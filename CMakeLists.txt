cmake_minimum_required(VERSION 3.16)
project(windmapper)

if( "$ENV{BUILD_WINDNINJA}")
file(
  DOWNLOAD
  https://github.com/cpm-cmake/CPM.cmake/releases/download/v0.38.3/CPM.cmake
  ${CMAKE_CURRENT_BINARY_DIR}/cmake/CPM.cmake
  EXPECTED_HASH SHA256=cc155ce02e7945e7b8967ddfaff0b050e958a723ef7aad3766d368940cb15494
)
include(${CMAKE_CURRENT_BINARY_DIR}/cmake/CPM.cmake)

CPMAddPackage(
  NAME WindNinja
  GITHUB_REPOSITORY firelab/windninja
  GIT_TAG 3.11.2
  OPTIONS
    "NINJA_QTGUI FALSE"
    "NINJAFOAM FALSE"
    "OPENMP_SUPPORT FALSE"
    "CMAKE_CXX_STANDARD 11"
)

endif()