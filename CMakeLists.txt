cmake_minimum_required(VERSION 3.16)
project(windmapper)
find_package(PythonExtensions REQUIRED)
file(
  DOWNLOAD
  https://github.com/cpm-cmake/CPM.cmake/releases/download/v0.38.3/CPM.cmake
  ${CMAKE_CURRENT_BINARY_DIR}/cmake/CPM.cmake
  EXPECTED_HASH SHA256=cc155ce02e7945e7b8967ddfaff0b050e958a723ef7aad3766d368940cb15494
)
include(${CMAKE_CURRENT_BINARY_DIR}/cmake/CPM.cmake)

if ("${CMAKE_CXX_COMPILER_ID}" STREQUAL "GNU")
    set(CONAN_LIB_STD "libstdc++11")
    message(STATUS "Detected gnu compiler, setting compiler.libcxx=${CONAN_LIB_STD}")
elseif ("${CMAKE_CXX_COMPILER_ID}" STREQUAL "Clang" OR "${CMAKE_CXX_COMPILER_ID}" STREQUAL "AppleClang")
    set(CONAN_LIB_STD "libc++")
    message(STATUS "Detected clang compiler, setting compiler.libcxx=${CONAN_LIB_STD}")
endif ()



CPMAddPackage(
  NAME WindNinja
  GITHUB_REPOSITORY Chrismarsh/windninja
  GIT_TAG 3.9.3
  OPTIONS
    "NINJA_QTGUI FALSE"
    "NINJAFOAM FALSE"
    "OPENMP_SUPPORT FALSE"
    "CMAKE_CXX_STANDARD 11"
)

file(COPY ${CMAKE_INSTALL_PREFIX}/lib/ DESTINATION ${PYTHON_PREFIX}/bin/lib/)
file(COPY ${CMAKE_INSTALL_PREFIX}/share/ DESTINATION ${PYTHON_PREFIX}/bin/share/)
file(COPY ${CMAKE_INSTALL_PREFIX}/bin/WindNinja_cli DESTINATION ${PYTHON_PREFIX}/bin/bin/)


# This approach won't work for installing outside of cmake install root
# install( DIRECTORY ${CMAKE_INSTALL_PREFIX}/lib/
#          DESTINATION ${PYTHON_PREFIX}/bin/lib/
# )
# install( DIRECTORY ${CMAKE_INSTALL_PREFIX}/share/
#          DESTINATION ${PYTHON_PREFIX}/bin/share/
# )
# install( PROGRAMS ${CMAKE_INSTALL_PREFIX}/bin/WindNinja_cli
#          DESTINATION ${PYTHON_PREFIX}/bin/bin/
# )
#
