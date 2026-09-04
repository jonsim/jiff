*** Settings ***
Resource    jiff.resource
Test Template    Renderer Highlights Source Syntax


*** Test Cases ***    RUNNER                         CONFIG RUNNER
Python Syntax         Run Python Jiff With Colour    Run Python Jiff With Config
Rust Syntax           Run Rust Jiff With Colour      Run Rust Jiff With Config


*** Keywords ***
Renderer Highlights Source Syntax
    [Documentation]    Exercises filename detection, `--syntax` and `--no-syntax` through the CLI.
    [Arguments]    ${runner}    ${config_runner}
    VAR    ${work_dir}    ${OUTPUT DIR}/jiff-system/${SUITE NAME}/${TEST NAME}
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
    Create File    ${config}    color.ansi16.syntax_keyword = { color = "blue" }
    ${detected} =    Run Keyword
    ...    ${runner}    --no-pager    ${left_python}    ${right_python}
    Output Should Contain ANSI Style    ${detected.stdout}    foreground=magenta

    ${explicit} =    Run Keyword
    ...    ${runner}    --no-pager    --syntax    python    ${left_text}    ${right_text}
    Output Should Contain ANSI Style    ${explicit.stdout}    foreground=magenta

    ${disabled} =    Run Keyword
    ...    ${runner}    --no-pager    --no-syntax    ${left_python}    ${right_python}
    Output Should Not Contain ANSI Style    ${disabled.stdout}    foreground=magenta

    ${configured} =    Run Keyword
    ...    ${config_runner}    ${config}    --no-pager    ${left_python}    ${right_python}
    Output Should Contain ANSI Style    ${configured.stdout}    foreground=blue

    VAR    ${config_highlight}    ${work_dir}/syntax-highlight-config.toml
    VAR    ${left_keyword}    ${work_dir}/keyword-before.py
    VAR    ${right_keyword}   ${work_dir}/keyword-after.py
    Create File    ${left_keyword}     def kermit(): pass
    Create File    ${right_keyword}    class kermit: pass
    Create File
    ...    ${config_highlight}
    ...    color.ansi16.syntax_keyword_highlight = { color = "bright_red" }

    ${configured_highlight} =    Run Keyword
    ...    ${config_runner}    ${config_highlight}    --no-pager    ${left_keyword}    ${right_keyword}
    Output Should Contain ANSI Style
    ...    ${configured_highlight.stdout}
    ...    foreground=bright_red
    ...    background=red
    Output Should Contain ANSI Style
    ...    ${configured_highlight.stdout}
    ...    foreground=bright_red
    ...    background=green
