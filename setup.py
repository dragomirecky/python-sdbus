# SPDX-License-Identifier: LGPL-2.1-or-later

# Copyright (C) 2020, 2021 igo95862
# Copyright (C) 2025, Alan Dragomirecký

# This file is part of aiodbus, a fork of python-sdbus.

# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.

# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.

# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301 USA
from __future__ import annotations

from os import environ
from subprocess import DEVNULL, PIPE
from subprocess import run as subprocess_run
from typing import List, Optional, Tuple

from setuptools import Extension, setup

c_macros: List[Tuple[str, Optional[str]]] = []


def get_libsystemd_version() -> int:
    process = subprocess_run(
        args=("pkg-config", "--modversion", "libsystemd"),
        stderr=DEVNULL,
        stdout=PIPE,
        check=True,
        text=True,
    )

    result_str = process.stdout
    # Version can either be like 250 or 250.10
    first_component = result_str.split(".")[0]

    return int(first_component)


if not environ.get("PYTHON_SDBUS_USE_IGNORE_SYSTEMD_VERSION"):
    systemd_version = get_libsystemd_version()

    if systemd_version < 246:
        c_macros.append(("LIBSYSTEMD_NO_VALIDATION_FUNCS", None))

    if systemd_version < 248:
        c_macros.append(("LIBSYSTEMD_NO_OPEN_USER_MACHINE", None))


def get_link_arguments() -> List[str]:
    process = subprocess_run(
        args=("pkg-config", "--libs-only-l", "libsystemd"),
        stderr=DEVNULL,
        stdout=PIPE,
        check=True,
    )

    result_str = process.stdout.decode("utf-8")

    return result_str.rstrip(" \n").split(" ")


link_arguments: List[str] = get_link_arguments()

if environ.get("PYTHON_SDBUS_USE_STATIC_LINK"):
    # Link statically against libsystemd and libcap
    link_arguments = [
        "-Wl,-Bstatic",
        *link_arguments,
        "-lcap",
        "-Wl,-Bdynamic",
        "-lrt",
        "-lpthread",
    ]

link_arguments.append("-flto")

compile_arguments: List[str] = ["-flto"]

use_limited_api = False

if environ.get("PYTHON_SDBUS_USE_LIMITED_API"):
    c_macros.append(("Py_LIMITED_API", "0x03070000"))
    use_limited_api = True


if __name__ == "__main__":
    with open("./README.md") as f:
        long_description = f.read()

    setup(
        packages=[
            "_sdbus",
            "aiodbus",
            "aiodbus.utils",
        ],
        package_dir={
            "aiodbus": "src/aiodbus",
            "_sdbus": "src/_sdbus",
        },
        package_data={
            "_sdbus": [
                "py.typed",
                "_sdbus.pyi",
                "_sdbus.h",
            ],
        },
        ext_modules=[
            Extension(
                "_sdbus",
                [
                    "src/_sdbus/_sdbus.c",
                    "src/_sdbus/_sdbus_bus.c",
                    "src/_sdbus/_sdbus_funcs.c",
                    "src/_sdbus/_sdbus_interface.c",
                    "src/_sdbus/_sdbus_message.c",
                ],
                extra_compile_args=compile_arguments,
                extra_link_args=link_arguments,
                define_macros=c_macros,
                py_limited_api=use_limited_api,
            )
        ],
    )
