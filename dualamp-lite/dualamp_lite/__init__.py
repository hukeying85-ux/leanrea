"""DualAMP-Lite: ESM-2 frozen backbone + multi-scale CNN + biophysical prior.

Code companion to the V3 plan
`抗菌肽深度学习方案_三次审查修订与最终执行版_V3_20261109_2245.docx`.

The pipeline is deliberately split into the three CLI steps named in the plan (§9):

    step1  build_dataset   ->  dualamp_lite.dataset   (D2, D3)
    step2  extract_features->  dualamp_lite.features  (D4)
    step3  train_and_eval  ->  dualamp_lite.train     (D5-D10, D15)

Everything is driven from one entry point:

    python -m dualamp_lite --help
"""

__version__ = "1.0.0"
__all__ = ["__version__"]
