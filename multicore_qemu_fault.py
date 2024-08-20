import os
import sys
import math
import time
import shutil
import argparse
import functools
import itertools
import subprocess
import multiprocessing
import yaml

from tqdm import tqdm
from rich.table import Table
from rich.console import Console


CONFIG_PATH = "config.yaml"
AVAILABLE_FAULT_MODELS = ("skip", "set")


def check_file_exists(*args):
    """Check that all files passed as arguments exists"""

    for file in args:
        if not os.path.isfile(file):
            print(f"[x] File {file} is missing !")
            sys.exit(1)


def create_snaphot(args, qemu_path, qemu_img_path, snapshot_plugin_path, qemu_options):
    """Create a snapshot right before the faulting address"""

    os.makedirs("experiment_disks", exist_ok=True)

    # First create a qcow2 disk
    print("[*] Creating qcow2 disk image")

    create_disk_command = [
        qemu_img_path,
        "create",
        "-f",
        "qcow2",
        "experiment_disks/disk1.qcow2",
        "32M",
    ]

    return_code = subprocess.run(
        create_disk_command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False
    ).returncode

    if return_code:
        print("[x] Error while creating qcow2 disk image")
        sys.exit(1)

    # Then run the VM and snapshot it at the address we should start faulting at
    print(f"[*] Running guest and snapshoting at address {hex(args.address)}")

    snapshot_plugin_command = f"{snapshot_plugin_path},addr={hex(args.address)}"
    snapshot_guest_command = [
        qemu_path,
        "-bios" if args.bios else "-kernel",
        args.programm,
        "-plugin",
        snapshot_plugin_command,
        "-drive",
        "if=none,format=qcow2,file=experiment_disks/disk1.qcow2",
        "-nographic",
    ]

    snapshot_guest_command.extend(qemu_options.split())

    return_code = subprocess.run(
        " ".join(snapshot_guest_command), shell=True, check=False
    ).returncode

    if return_code:
        print("[x] Error while snapshoting guest !")
        sys.exit(1)


def duplicate_disk(n):
    """Duplicate the snapshot disk `n` time as different instances cannot use the same qcow2 disk"""

    for i in range(1, n):
        shutil.copyfile(
            "experiment_disks/disk1.qcow2", f"experiment_disks/disk{i+1}.qcow2"
        )


def run_one_instance(command_line, queue):
    """Run one QEMU instance, results will be passed through the queue"""

    with subprocess.Popen(
        command_line,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=1,
        universal_newlines=True
    ) as p:
        for line in p.stderr:
            queue.put(line)

    queue.put("done")


def run_instances(args, qemu_path, qemu_fault_plugin_path, qemu_options, n):
    """Run `n` QEMU instances with the fault plugin"""

    commands = []

    for i in range(n):
        fault_plugin_command = (
            f"{qemu_fault_plugin_path},fault_window={args.fault_window},fault_offset={i}"
            f",fault_step={n},end_addr={hex(args.end_address)},error_addr={hex(args.error_address)}"
            f",timeout={args.insn_timeout},faulted_addr={hex(args.fault_address)}"
            f",num_fault={args.num_fault},strict={'on' if args.strict else 'off'}"
            f",fault_model={args.fault_model}"
        )

        if args.fault_model == "set":
            fault_plugin_command += f",set_value={args.set_value}"

        qemu_command = [
            qemu_path,
            "-display",
            "none",
            "-serial",
            "none",
            "-bios" if args.bios else "-kernel",
            args.programm,
            "-drive",
            f"if=none,format=qcow2,file=experiment_disks/disk{i+1}.qcow2",
            "-loadvm",
            "snapshotfault",
            "-d",
            "plugin",
            "-plugin",
            fault_plugin_command,
        ]

        qemu_command.extend(qemu_options.split())
        commands.append(qemu_command)

    manager = multiprocessing.Manager()
    shared_queue = manager.Queue()

    terminated_instances = 0
    total_campaign = math.comb(args.fault_window, args.num_fault)
    pbar = tqdm(total=total_campaign, desc="Progress", leave=False)
    commands = zip(commands, itertools.repeat(shared_queue))

    with multiprocessing.Pool(processes=n) as pool:
        # Statistics
        fault_count = 0
        crash_count = 0
        timeout_count = 0
        end_address_reached_count = 0
        begin_time = time.time()

        r = pool.starmap_async(run_one_instance, commands)

        while terminated_instances != n:
            msg = shared_queue.get()

            if msg == "step\n":
                pbar.update(1)

            elif msg == "done":
                terminated_instances += 1

            elif msg == "fault\n":
                fault_count += 1

            elif msg == "timeout\n":
                timeout_count += 1

            elif msg == "endaddr\n":
                end_address_reached_count += 1

            elif msg == "erroraddr\n":
                crash_count += 1

            else:
                pbar.write(msg, end="")

        r.wait()

    end_time = time.time()
    pbar.close()
    print(f'[*] All faults injected in {end_time - begin_time}s')
    return fault_count, crash_count, timeout_count, end_address_reached_count


def display_results(results):
    """Display fault results"""

    total = sum(results)
    table = Table(title="Results")

    table.add_column()
    table.add_column("Total")
    table.add_column("Percent")

    for result_type, result in zip(["Fault", "Crash", "Timeout", "Reach end"], results):
        table.add_row(result_type, str(result), f"{result / total * 100:.3f} %")

    table.add_row("", str(total), "")

    console = Console()
    console.print(table)


def parse_arguments():
    """Parse command line arguments"""

    parser = argparse.ArgumentParser(
        description="Try to fault a given binary at every possible injection \
        offsets specified in the following arguments and print results"
    )

    parser.add_argument(
        "programm", help="Path to the programm that will be faulted", type=str
    )

    parser.add_argument(
        "-fw",
        "--fault_window",
        help="Faulted instructions range size",
        type=functools.partial(int, base=0),
        required=True
    )

    parser.add_argument(
        "-a",
        "--address",
        help="Address of the instruction to start faulting at",
        type=functools.partial(int, base=0),
        required=True
    )

    parser.add_argument(
        "-fa",
        "--fault_address",
        help="Consider a fault configuration as valid if this address is reached",
        type=functools.partial(int, base=0),
        required=True
    )

    parser.add_argument(
        "-ea",
        "--end_address",
        help="Consider a fault configuration had no effect if this address is reached",
        type=functools.partial(int, base=0),
        required=True
    )

    parser.add_argument(
        "-erra",
        "--error_address",
        help="Consider a fault configuration crashed the target if this address is reached",
        type=functools.partial(int, base=0),
        required=True
    )

    parser.add_argument(
        "-ito",
        "--insn_timeout",
        help="Maximum number of instructions to execute before considering the fault \
              configuration led to a timeout if none of the trigger addresses were reached",
        type=functools.partial(int, base=0),
        required=True
    )

    parser.add_argument(
        "-nf",
        "--num_fault",
        help="Number of fault to inject in a campaign, default is a single fault. \
        WARNING: run time increase exponentially as you increase this value",
        type=functools.partial(int, base=0),
        default=1
    )

    parser.add_argument(
        "-fm",
        "--fault_model",
        help="Fault model to apply, available models are: skip (transient instruction skip) \
        and set (overwrite destination registers values)",
        type=str,
        choices=AVAILABLE_FAULT_MODELS,
        default="skip"
    )

    parser.add_argument(
        "-sv",
        "--set_value",
        help="Value written registers should be replaced by when the fault model is 'set'",
        type=functools.partial(int, base=0),
        default=0
    )

    parser.add_argument(
        "-bios",
        help="Pass the programm using -bios option to qemu rather than -kernel",
        action="store_true",
        default=False
    )

    parser.add_argument(
        "-strict",
        help="Display fault information only if the fault address was reach exactly after \
        'num_fault' injection",
        action="store_true",
        default=False
    )

    return parser.parse_args()


def check_arguments(args):
    """Check arguments validity, exit if they are invalid"""
    if args.num_fault > args.fault_window:
        print("[x] 'num_fault' cannot be higher than 'fault_window'")
        sys.exit(1)


def get_guest_cpu_count():
    """Determine how many cores are used by a QEMU machine"""

    # TODO: Write a plugin for this as there is no option in QEMU to get this information.
    #       As the fault plugin does not yet supported multi-core targets, we return 1 for now.
    return 1


def main():
    """Main function that will run everything"""
    args = parse_arguments()
    check_arguments(args)

    if not os.path.isfile(CONFIG_PATH):
        print(f"[x] Could not find {CONFIG_PATH}")
        sys.exit(1)

    with open(CONFIG_PATH, "r") as f:
        config = yaml.safe_load(f)

    qemu_path = config["qemu_executable_path"]
    qemu_img_path = config["qemu_img_executable_path"]
    snapshot_plugin_path = config["qemu_snapshot_plugin_path"]
    fault_plugin_path = config["qemu_fault_plugin_path"]
    qemu_opts = config["qemu_options"]

    check_file_exists(
        args.programm, qemu_path, qemu_img_path, snapshot_plugin_path, fault_plugin_path
    )

    host_cpu_count = multiprocessing.cpu_count()
    guest_cpu_count = get_guest_cpu_count()

    if host_cpu_count is None:
        host_cpu_count = guest_cpu_count

    print(f"[*] Host CPU count: {host_cpu_count}")
    print(f"[*] Guest CPU count: {guest_cpu_count}")

    total_campaign = math.comb(args.fault_window, args.num_fault)

    # Make sure we do not start more instances than the total number of campaign
    # to run even though this is not likely to happen
    instances_to_run = min(host_cpu_count // guest_cpu_count, total_campaign)

    print(f"[*] Running experiment on {instances_to_run} QEMU instances")

    create_snaphot(args, qemu_path, qemu_img_path, snapshot_plugin_path, qemu_opts)
    print("[*] Successfully created snapshot for the experiment !")

    print("[*] Duplicating the disk containing snapshot for each instances")
    duplicate_disk(instances_to_run)

    results = run_instances(args, qemu_path, fault_plugin_path, qemu_opts, instances_to_run)
    display_results(results)


if __name__ == "__main__":
    main()
