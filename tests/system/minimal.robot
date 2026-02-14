*** Settings ***
Resource    jiff.resource
Test Template    Jiff Files

*** Test Cases ***  LEFT              RIGHT             EXPECTATION
01_02               minimal/01.txt    minimal/02.txt    minimal/results/01_02.diff
01_03               minimal/01.txt    minimal/03.txt    minimal/results/01_03.diff
01_04               minimal/01.txt    minimal/04.txt    minimal/results/01_04.diff
01_09               minimal/01.txt    minimal/09.txt    minimal/results/01_09.diff
02_11               minimal/02.txt    minimal/11.txt    minimal/results/02_11.diff
02_12               minimal/02.txt    minimal/12.txt    minimal/results/02_12.diff
02_13               minimal/02.txt    minimal/13.txt    minimal/results/02_13.diff
01_02_side_by_side  minimal/01.txt    minimal/02.txt    minimal/results/01_02.sbsdiff    True
01_03_side_by_side  minimal/01.txt    minimal/03.txt    minimal/results/01_03.sbsdiff    True
01_04_side_by_side  minimal/01.txt    minimal/04.txt    minimal/results/01_04.sbsdiff    True
01_09_side_by_side  minimal/01.txt    minimal/09.txt    minimal/results/01_09.sbsdiff    True
02_11_side_by_side  minimal/02.txt    minimal/11.txt    minimal/results/02_11.sbsdiff    True
02_12_side_by_side  minimal/02.txt    minimal/12.txt    minimal/results/02_12.sbsdiff    True
02_13_side_by_side  minimal/02.txt    minimal/13.txt    minimal/results/02_13.sbsdiff    True
