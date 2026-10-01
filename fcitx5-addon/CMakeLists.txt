cmake_minimum_required(VERSION 3.16)
project(fcitx5-voiceim LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(Fcitx5Core REQUIRED)

add_library(voiceim MODULE voiceim.cpp)
target_link_libraries(voiceim PRIVATE Fcitx5::Core)

install(TARGETS voiceim LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR}/fcitx5)
