# QEMU Fault Tool

A QEMU based tool to achieve exhaustive fault injection on various targets. This tool aim to support as much target as possible. Currently supported architectures are those supported by QEMU (ARM, i386/x86-64, MIPS, PowerPC, RISCV32/64, AVR ...).

## Prerequisites

In order to build QEMU you need to install some packages. This can be done with the following command:

```shell
$ sudo apt install git libglib2.0-dev libfdt-dev libpixman-1-dev zlib1g-dev ninja-build libcapstone-dev
```

Install the Python script dependencies using the following command:

```shell
$ pip install -r requirements.txt
```

If you plan compiling the verifyPin example you need to install the ARM GNU cross compilation toolchain available at https://developer.arm.com/downloads/-/arm-gnu-toolchain-downloads

## Compilation

Clone this repository:

```shell
$ git clone --recurse-submodules git@github.com:shml1n/qemu-fault-tool.git
```

Compile QEMU:

```shell
$ cd qemu
$ mkdir build
$ cd build
$ ../configure
$ make -j $(nproc)
```

## Usage

### The VerifyPin example

**Optional**: To compile the program by yourself simply use the following commands

```shell
$ cd example/verifyPin
$ make
```

Faulting the PIN comparison can be achieved with the following command line:

```shell
$ python3 multicore_qemu_fault.py -fw 3635 -a 0x800028c -fa 0x800029a -ea 0x80002ea -erra 0x8000408 -ito 3635 -fm skip example/verifyPin/verifyPin.elf
```

**Note**: if you compiled the program by yourself the addresses may differ based on your cross compilation toolchain version.

### The U-Boot example

Before faulting U-Boot you have to uncomment the following lines in `config.yaml`:

```yaml
# Uncomment this to fault u-boot
# qemu_executable_path: "qemu/build/qemu-system-aarch64"
...
# Uncomment this to fault u-boot
# qemu_options: "-M virt -cpu cortex-a57 -m 24M"
```

Faulting the U-Boot password comparison can then be achieved with the following command line:

```shell
$ python3 multicore_qemu_fault.py -fw 800000 -a 0x417675f8 -fa 0x4175ec9c -ea 0x41765f70 -erra 0x41765f70 -ito 800000 example/u-boot/bootloader.bin -bios
```

**Note**: Addresses were found using the Ghidra decompiler.
