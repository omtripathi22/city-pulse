cmake_minimum_required(VERSION 3.20)

project(citypulse_core LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

add_library(citypulse_core SHARED citypulse_core.cpp)

target_compile_features(citypulse_core PRIVATE cxx_std_17)

if(MSVC)
    target_compile_options(citypulse_core PRIVATE /W4 /EHsc)
else()
    target_compile_options(citypulse_core PRIVATE -Wall -Wextra -Wpedantic)
endif()

set_target_properties(citypulse_core PROPERTIES
    OUTPUT_NAME "citypulse_core"
    RUNTIME_OUTPUT_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
    LIBRARY_OUTPUT_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
)

