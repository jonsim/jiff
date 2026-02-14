*** Settings ***
Resource    jiff.resource
Test Template    Jiff Files

*** Test Cases ***    LEFT              RIGHT             EXPECTATION
01_02                 minimal/01.txt    minimal/02.txt    minimal/results/01_02.diff
01_03                 minimal/01.txt    minimal/03.txt    minimal/results/01_03.diff
01_04                 minimal/01.txt    minimal/04.txt    minimal/results/01_04.diff
01_09                 minimal/01.txt    minimal/09.txt    minimal/results/01_09.diff
