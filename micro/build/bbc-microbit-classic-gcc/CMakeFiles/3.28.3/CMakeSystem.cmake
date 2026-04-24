set(CMAKE_HOST_SYSTEM "Linux-6.12.76-linuxkit")
set(CMAKE_HOST_SYSTEM_NAME "Linux")
set(CMAKE_HOST_SYSTEM_VERSION "6.12.76-linuxkit")
set(CMAKE_HOST_SYSTEM_PROCESSOR "x86_64")

include("/workspaces/microbit-samples/build/bbc-microbit-classic-gcc/toolchain.cmake")

set(CMAKE_SYSTEM "mbedOS-1")
set(CMAKE_SYSTEM_NAME "mbedOS")
set(CMAKE_SYSTEM_VERSION "1")
set(CMAKE_SYSTEM_PROCESSOR "armv7-m")

set(CMAKE_CROSSCOMPILING "TRUE")

set(CMAKE_SYSTEM_LOADED 1)
