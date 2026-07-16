# SewEasy: Programming Parametric Sewing Patterns

![Examples of garments sampled from the SewEasy configurator](https://github.com/thomashayama/SewEasy/raw/main/assets/img/header.png)

SewEasy is a modular programming framework for designing parametric sewing patterns, with a browser-based garment configurator and tools for draping patterns into simulated 3D garments.

SewEasy is a fork of [GarmentCode](https://github.com/maria-korosteleva/GarmentCode) by Maria Korosteleva et al., the official implementation of [GarmentCode: Programming Parametric Sewing Patterns](https://igl.ethz.ch/projects/garmentcode/) (SIGGRAPH Asia 2023) and [GarmentCodeData: A Dataset of 3D Made-to-Measure Garments With Sewing Patterns](https://igl.ethz.ch/projects/GarmentCodeData/) (ECCV 2024). All credit for the original system belongs to its authors — see [Attribution](#attribution) below.

> The body measurements part of the upstream project lives here: https://github.com/mbotsch/GarmentMeasurements

## Documents

1. [Installation](https://github.com/thomashayama/SewEasy/blob/main/docs/Installation.md)
2. [Running Configurator](https://github.com/thomashayama/SewEasy/blob/main/docs/Running_seweasy.md)
3. [Running Data Generation (warp)](https://github.com/thomashayama/SewEasy/blob/main/docs/Running_data_generation.md)
4. [Body measurements](https://github.com/thomashayama/SewEasy/blob/main/docs/Body%20Measurements%20GarmentCode.pdf)
5. [Dataset documentation](https://www.research-collection.ethz.ch/handle/20.500.11850/673889)
6. [Running Old Maya+Qualoth tools](https://github.com/thomashayama/SewEasy/blob/main/docs/Running_Maya_Qualoth.md)

## Navigation

### Library

[seweasy](https://github.com/thomashayama/SewEasy/tree/main/seweasy) is the core library, described in the GarmentCode paper. It contains the base types (Edge, Panel, Component, Interface, etc.), as well as edge factory and various helpers and operators that help you design sewing patterns.

See [Installation instructions](https://github.com/thomashayama/SewEasy/tree/main/docs/Installation.md) before use.

### Examples

* [assets/garment_programs/](https://github.com/thomashayama/SewEasy/tree/main/assets/garment_programs/) contains the code of garment components designed using the seweasy library.
* [assets/design_params/](https://github.com/thomashayama/SewEasy/tree/main/assets/design_params/), [assets/bodies/](https://github.com/thomashayama/SewEasy/tree/main/assets/bodies/) contain examples of design and body measurements presets. They can be used in both the SewEasy GUI and the `test_seweasy.py` script.

> NOTE: [assets/design_params/default.yaml](https://github.com/thomashayama/SewEasy/blob/main/assets/design_params/default.yaml) is the setup used by GUI on load. Changing this file results in changes in the GUI initial state =)

## Attribution

This project is a fork of [GarmentCode](https://github.com/maria-korosteleva/GarmentCode) (MIT License, Copyright (c) 2024 Maria Korosteleva). The original system was created by:

* [Maria Korosteleva](https://github.com/maria-korosteleva)
* [Jasmin Koller](https://github.com/JasminKoller)
* [Yuhan Zhang](https://github.com/yuhan-zh)
* [Yuhan Liu](https://github.com/yuhanliu-tech)
* [Ami Beuret](https://github.com/amibeuret)
* [Olga Sorkine-Hornung](https://igl.ethz.ch/people/sorkine/index.php)

The body measurements team developed [GarmentMeasurements](https://github.com/mbotsch/GarmentMeasurements):
* [Fabian Kemper](https://github.com/fabiankemper)
* [Stephan Wenninger](https://github.com/stephan-wenninger)
* [Mario Botsch](https://github.com/mbotsch)

## Citation

If you are using this system in your research, please cite the original papers:

```bibtex
@inproceedings{GarmentCodeData:2024,
  author = {Korosteleva, Maria and Kesdogan, Timur Levent and Kemper, Fabian and Wenninger, Stephan and Koller, Jasmin and Zhang, Yuhan and Botsch, Mario and Sorkine-Hornung, Olga},
  title = {{GarmentCodeData}: A Dataset of 3{D} Made-to-Measure Garments With Sewing Patterns},
  booktitle={Computer Vision -- ECCV 2024},
  year = {2024},
  keywords = {sewing patterns, garment reconstruction, dataset},
}
```

```bibtex
@article{GarmentCode2023,
  author = {Korosteleva, Maria and Sorkine-Hornung, Olga},
  title = {{GarmentCode}: Programming Parametric Sewing Patterns},
  year = {2023},
  issue_date = {December 2023},
  publisher = {Association for Computing Machinery},
  address = {New York, NY, USA},
  volume = {42},
  number = {6},
  doi = {10.1145/3618351},
  journal = {ACM Transaction on Graphics},
  note = {SIGGRAPH ASIA 2023 issue},
  numpages = {16},
  keywords = {sewing patterns, garment modeling}
}
```

## Issues, questions, suggestions

Please post issues and questions about SewEasy to [GitHub Issues](https://github.com/thomashayama/SewEasy/issues). For the original GarmentCode project, see the [upstream repository](https://github.com/maria-korosteleva/GarmentCode).
