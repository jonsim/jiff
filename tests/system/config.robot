*** Settings ***
Resource    jiff.resource
Test Template    Renderer Loads Custom Colours

*** Test Cases ***    RUNNER
Python Config         Run Python Jiff With Config
Rust Config           Run Rust Jiff With Config

*** Keywords ***
Renderer Loads Custom Colours
    [Documentation]    Checks a TOML palette is applied in both output modes.
    [Arguments]    ${runner}
    VAR    ${config}    ${TEMPDIR}/jiff-colour-test.toml
    VAR    ${config_contents}
    ...    [color]
    ...    \nadd = { color = "blue", bold = true }
    ...    \nadd_highlight = { color = "yellow", bgcolor = "blue" }
    ...    \noverlap_highlight = { color = "white", bgcolor = "blue" }
    VAR    ${base_dir}    ${CURDIR}/../..
    VAR    ${first}    ${base_dir}/testcases/minimal/02.txt
    VAR    ${first_hello}    ${base_dir}/testcases/minimal/03.txt
    Create File    ${config}    ${config_contents}
    ${inline} =    Run Keyword
    ...    ${runner}    ${config}    --inline    ${first}    ${first_hello}
    ${side_by_side} =    Run Keyword
    ...    ${runner}    ${config}    ${first}    ${first_hello}
    Output Uses Custom Colours    ${inline.stdout}
    Output Uses Custom Colours    ${side_by_side.stdout}

    VAR    ${local}     ${base_dir}/testcases/threeway/overlapping/local.py
    VAR    ${base}      ${base_dir}/testcases/threeway/overlapping/base.py
    VAR    ${remote}    ${base_dir}/testcases/threeway/overlapping/remote.py
    ${three_way} =    Run Keyword
    ...    ${runner}    ${config}    --no-syntax    ${local}    ${base}    ${remote}
    Output Uses Custom Overlap Colour    ${three_way.stdout}

Output Uses Custom Colours
    [Arguments]    ${output}
    ${blue} =    Evaluate    chr(27) + "[1;34m"
    ${highlight} =    Evaluate    chr(27) + "[33;44m"
    ${highlight_reordered} =    Evaluate    chr(27) + "[44;33m"
    Should Contain    ${output}    ${blue}
    Should Contain Any    ${output}    ${highlight}    ${highlight_reordered}

Output Uses Custom Overlap Colour
    [Arguments]    ${output}
    ${overlap} =    Evaluate    chr(27) + "[37;44m"
    ${overlap_reordered} =    Evaluate    chr(27) + "[44;37m"
    Should Contain Any    ${output}    ${overlap}    ${overlap_reordered}
