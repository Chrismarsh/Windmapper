#!/bin/bash

set -e

if  [ "$TRAVIS_OS_NAME" = "osx" ]; then

    bash -c 'echo $pyv'
    bash -c 'echo $TRAVIS_PYTHON_VERSION'
    bash -c 'echo $TRAVIS_OS_NAME'

    brew update || true

    cd /usr/local/Homebrew/Library/Taps/homebrew/homebrew-core/Formula
    git checkout 531a642ed504eb78890d8a5862086edd2572f2d4 -- gdal.rb
    HOMEBREW_NO_AUTO_UPDATE=1 brew install gdal
    brew pin gdal
    brew upgrade || true
#    brew install gdal@3.1.0 # || brew upgrade gdal

   if [ "$test_conda" != "1" ]; then
      brew outdated pyenv || brew upgrade pyenv
      brew install pyenv-virtualenv

      eval "$(pyenv init -)"
      pyenv install $pyv
      pyenv virtualenv $pyv Windmapper
      pyenv rehash
      pyenv activate Windmapper
  fi

else
  sudo add-apt-repository ppa:ubuntu-toolchain-r/test -y;
  sudo apt-get update -qq
  sudo apt-get install g++-7
  sudo apt-get install libgdal-dev
  sudo apt-get install python-gdal
  sudo apt-get install gdal-bin

fi

if [ "$test_conda" = "1" ]; then
  if [ "$TRAVIS_OS_NAME" = "osx" ]; then
    wget -O ~/miniconda.sh https://repo.anaconda.com/miniconda/Miniconda3-latest-MacOSX-x86_64.sh
  else
    wget -O ~/miniconda.sh https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh 
  fi

  bash ~/miniconda.sh -b -p $HOME/conda
  source $HOME/conda/bin/activate
  conda init
  conda update -y --all
  conda create -y --name Windmapper python=$pyv

fi