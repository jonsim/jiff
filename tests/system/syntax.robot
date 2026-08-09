*** Settings ***
Resource    jiff.resource
Test Template    Renderer Highlights Source Syntax


*** Test Cases ***    RUNNER                         CONFIG RUNNER
Python Syntax         Run Python Jiff With Colour    Run Python Jiff With Config
Rust Syntax           Run Rust Jiff With Colour      Run Rust Jiff With Config


*** Keywords ***
Renderer Highlights Source Syntax
    [Documentation]    Checks detection, override and opt-out at the real CLI boundary.
    [Arguments]    ${runner}    ${config_runner}
    VAR    ${work_dir}    ${TEMPDIR}/${TEST NAME}
    VAR    ${left_python}    ${work_dir}/muppets-before.py
    VAR    ${right_python}    ${work_dir}/muppets-after.py
    VAR    ${left_text}    ${work_dir}/muppets-before.txt
    VAR    ${right_text}    ${work_dir}/muppets-after.txt
    VAR    ${config}    ${work_dir}/syntax-config.toml
    Create Directory    ${work_dir}
    Create File    ${left_python}    def kermit(): return "green"
    Create File    ${right_python}    def kermit(): return "blue"
    Copy File    ${left_python}    ${left_text}
    Copy File    ${right_python}    ${right_text}
    Create File    ${config}    color.syntax_keyword = { color = "blue" }
    ${magenta} =    Evaluate    chr(27) + "[35m"
    ${blue} =    Evaluate    chr(27) + "[34m"

    ${detected} =    Run Keyword
    ...    ${runner}    --no-pager    ${left_python}    ${right_python}
    Should Contain    ${detected.stdout}    ${magenta}

    ${explicit} =    Run Keyword
    ...    ${runner}    --no-pager    --syntax    python    ${left_text}    ${right_text}
    Should Contain    ${explicit.stdout}    ${magenta}

    ${disabled} =    Run Keyword
    ...    ${runner}    --no-pager    --no-syntax    ${left_python}    ${right_python}
    Should Not Contain    ${disabled.stdout}    ${magenta}

    ${configured} =    Run Keyword
    ...    ${config_runner}    ${config}    --no-pager    ${left_python}    ${right_python}
    Should Contain    ${configured.stdout}    ${blue}
