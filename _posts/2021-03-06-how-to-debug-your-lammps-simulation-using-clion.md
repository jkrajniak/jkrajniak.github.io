---
layout: post
title: "How to debug your LAMMPS simulation using CLion"
date: 2021-03-06
description: "From time to time I need to debug LAMMPS code to find out why a simulation does not work as expected...."
tags:
  - lammps
  - debugging
  - clion
  - cpp
canonical_url: "https://dev.to/jkrajniak/how-to-debug-your-lammps-simulation-using-clion-mmo"
image: "/assets/images/posts/how-to-debug-your-lammps-simulation-using-clion/180f327de7.png"
---

From time to time I need to debug [LAMMPS](https://lammps.sandia.gov/doc/Intro.html) code to find out why a simulation does not work as expected. The easiest way is to jump into the runtime using a debugger. Although `gdb` does the job, it is not the most intuitive and easy to use the tool. 

In my daily work, whenever I can, I use JetBrains toolbox, for C++ programming - [CLion](https://www.jetbrains.com/clion/). It definitely simplifies work, allowing as well to easy debug the code.

LAMMPS uses [CMake](https://cmake.org/) to control the build process. Fortunately for us, CLion integrates with CMake projects very well.

So let's start.

# Setup project

1. Open CLion, if you end up in the Welcome Window then click on **Open**
![welcome-screen](/assets/images/posts/how-to-debug-your-lammps-simulation-using-clion/6bd78b30c9.png)
and select the root of LAMMPS directory.

![select-project](/assets/images/posts/how-to-debug-your-lammps-simulation-using-clion/e97ffac38b.png)
If you end up in the main window with an already opened project, you can go to **Open :arrow_right: File :arrow_right: Open...** and select the root of LAMMPS directory.

2\. To enable CMake project, open `cmake/CMakeLists.txt`. You should see in the editor window on the top link to **Load CMake project**, click on it.
![Alt Text](/assets/images/posts/how-to-debug-your-lammps-simulation-using-clion/8f5e3092f6.png)

That is it, now you can compile your LAMMPS code directly from CLion, run and debug.

# Enable/disable different compilation options

LAMMPS contains multiple packages, which enables various of capabilities. This modular design allows compiling the final binary executables with only these functions that are needed to simulate your system.
You can enable/disable features and settings by *-D* argument. The other, more convenient option, is to use [CMake presets](https://lammps.sandia.gov/doc/Build_package.html#cmake-presets), which contains predefined variables.

The preset can be enabled from command line:
```sh
$ mkdir build; cd build
$ cmake -C ../cmake/presets/minimal.cmake ../cmake
```
and to enable multiple one at the same time
```sh
$ cmake -C ../cmake/presets/nolib.cmake -C ../cmake/presets/gcc.cmake -C ../cmake/presets/most.cmake  ../cmake
```

You can attach the same settings in the Clion project configuration by putting CMake command line option in *CMake options* field.
![Alt Text](/assets/images/posts/how-to-debug-your-lammps-simulation-using-clion/1883eb998b.png)

# Run your simulation script

Now, when we set up our project, we can run our simulation script. 

The easiest way is to make a copy of an existing configuration and include the simulation script.
Go to **Run :arrow_right: Edit Configurations...**
![Alt Text](/assets/images/posts/how-to-debug-your-lammps-simulation-using-clion/a6c5dc30a0.png)

In the list of targets, search for **lmp** and click on **Copy** icon, change the name of the target.
Next, set the **Working directory** to the path where your simulation scripts are located. In the **Program arguments** you can specify which simulation script to run, e.g. `-in in.lmp` if your simulation script is in `in.lmp` file. 

# Run debugger

Running debugger is pretty simple. In the main window select the target to run, and click on the Debug icon.
![Alt Text](/assets/images/posts/how-to-debug-your-lammps-simulation-using-clion/8355420cd6.png)

-----

I have guided you step by step on how to set up debugging for LAMMPS package. However, you can debug your [GROMACS](https://manual.gromacs.org/documentation/) or [ESPResSo++](https://github.com/espressopp/espressopp) simulations.

-----

Happy debugging!

---

If you liked the post, then you can [buy me a coffee](https://www.buymeacoffee.com/jkrajniak). Thanks in advance.