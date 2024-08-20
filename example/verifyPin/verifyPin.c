/*
 * This file is part of the libopencm3 project.
 *
 * Copyright (C) 2015 Chuck McManis <cmcmanis@mcmanis.com>
 *
 * This library is free software: you can redistribute it and/or modify
 * it under the terms of the GNU Lesser General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * This library is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU Lesser General Public License for more details.
 *
 * You should have received a copy of the GNU Lesser General Public License
 * along with this library.  If not, see <http://www.gnu.org/licenses/>.
 *
 */

#include <libopencm3/stm32/gpio.h>
#include <libopencm3/stm32/rcc.h>
#include <libopencm3/stm32/usart.h>

#define SEND_BUFFER_SIZE 256

static void usart_setup(void) {
  gpio_set_mode(GPIOA, GPIO_MODE_OUTPUT_50_MHZ, GPIO_CNF_OUTPUT_ALTFN_PUSHPULL,
                GPIO_USART1_TX);
  gpio_set_mode(GPIOA, GPIO_MODE_INPUT, GPIO_CNF_INPUT_FLOAT, GPIO_USART1_RX);

  /* Setup UART parameters. */
  usart_set_baudrate(USART1, 115200);
  usart_set_databits(USART1, 8);
  usart_set_stopbits(USART1, USART_STOPBITS_1);
  usart_set_mode(USART1, USART_MODE_TX_RX);
  usart_set_parity(USART1, USART_PARITY_NONE);
  usart_set_flow_control(USART1, USART_FLOWCONTROL_NONE);

  /* Finally enable the USART. */
  usart_enable(USART1);
}

static void usart_send_string(uint32_t usart, uint8_t *string,
                              uint16_t str_size) {
  uint16_t iter = 0;
  do {
    usart_send_blocking(usart, string[iter++]);
  } while (string[iter] != 0 && iter < str_size);
}

static void usart_get_string(uint32_t usart, uint8_t *out_string,
                             uint16_t str_max_size) {
  uint8_t sign = 0;
  uint16_t iter = 0;

  while (iter < str_max_size) {
    sign = usart_recv_blocking(usart);

    if (sign != '\n' && sign != '\r')
      out_string[iter++] = sign;
    else {
      out_string[iter] = 0;
      usart_send_string(USART1, (uint8_t *)"\r\n", 3);
      break;
    }
  }
}

int main(void) {
  uint8_t recv_buf[SEND_BUFFER_SIZE];

  usart_setup();

  while (1) {
    usart_send_string(USART1, (uint8_t *)"Please enter a 1-digit PIN: \r\n",
                      SEND_BUFFER_SIZE);
    usart_get_string(USART1, recv_buf, SEND_BUFFER_SIZE);

    if (recv_buf[0] == '0') {
      usart_send_string(USART1, (uint8_t *)"Congrats you won !",
                        SEND_BUFFER_SIZE);
    } else {
      usart_send_string(USART1, (uint8_t *)"Invalid pin !", SEND_BUFFER_SIZE);
    }

    usart_send_string(USART1, (uint8_t *)"\r\n", 3);

    // Clear the receive buffer
    for (int i = 0; i < SEND_BUFFER_SIZE; i++) {
      recv_buf[i] = 0;
    }
  }

  return 0;
}
