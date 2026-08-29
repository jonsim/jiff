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
14_15               minimal/14.txt    minimal/15.txt    minimal/results/14_15.diff
16_17               minimal/16.txt    minimal/17.txt    minimal/results/16_17.diff
18_19               minimal/18.txt    minimal/19.txt    minimal/results/18_19.diff
20_21               minimal/20.txt    minimal/21.txt    minimal/results/20_21.diff
22_23               minimal/22.txt    minimal/23.txt    minimal/results/22_23.diff
24_25               minimal/24.txt    minimal/25.txt    minimal/results/24_25.diff
01_11               minimal/01.txt    minimal/11.txt    minimal/results/01_11.diff
01_12               minimal/01.txt    minimal/12.txt    minimal/results/01_12.diff
01_13               minimal/01.txt    minimal/13.txt    minimal/results/01_13.diff
01_02_side_by_side  minimal/01.txt    minimal/02.txt    minimal/results/01_02.sbsdiff    True
01_03_side_by_side  minimal/01.txt    minimal/03.txt    minimal/results/01_03.sbsdiff    True
01_04_side_by_side  minimal/01.txt    minimal/04.txt    minimal/results/01_04.sbsdiff    True
01_09_side_by_side  minimal/01.txt    minimal/09.txt    minimal/results/01_09.sbsdiff    True
01_11_side_by_side  minimal/01.txt    minimal/11.txt    minimal/results/01_11.sbsdiff    True
01_12_side_by_side  minimal/01.txt    minimal/12.txt    minimal/results/01_12.sbsdiff    True
01_13_side_by_side  minimal/01.txt    minimal/13.txt    minimal/results/01_13.sbsdiff    True
02_11_side_by_side  minimal/02.txt    minimal/11.txt    minimal/results/02_11.sbsdiff    True
02_12_side_by_side  minimal/02.txt    minimal/12.txt    minimal/results/02_12.sbsdiff    True
02_13_side_by_side  minimal/02.txt    minimal/13.txt    minimal/results/02_13.sbsdiff    True
14_15_side_by_side  minimal/14.txt    minimal/15.txt    minimal/results/14_15.sbsdiff    True
16_17_side_by_side  minimal/16.txt    minimal/17.txt    minimal/results/16_17.sbsdiff    True
18_19_side_by_side  minimal/18.txt    minimal/19.txt    minimal/results/18_19.sbsdiff    True
20_21_side_by_side  minimal/20.txt    minimal/21.txt    minimal/results/20_21.sbsdiff    True
22_23_side_by_side  minimal/22.txt    minimal/23.txt    minimal/results/22_23.sbsdiff    True
24_25_side_by_side  minimal/24.txt    minimal/25.txt    minimal/results/24_25.sbsdiff    True
