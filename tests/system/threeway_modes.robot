*** Settings ***
Resource    jiff.resource


*** Test Cases ***
Inline Renderers Agree
    Three-way Inline Renderers Agree

Binary Inputs Use Labelled Comparisons
    Three-way Binary Renderers Agree

Python Composes Syntax And Diff Colours
    Three-way Colours Compose    Run Python Jiff With Colour

Rust Composes Syntax And Diff Colours
    Three-way Colours Compose    Run Rust Jiff With Colour


*** Keywords ***
Three-way Inline Renderers Agree
    [Documentation]    Checks the two labelled comparisons used by `--inline`.
    VAR    ${root}    ${CURDIR}/../../testcases/threeway/independent
    VAR    @{args}
    ...    --inline
    ...    --no-color
    ...    --no-pager
    ...    -U2
    ...    ${root}/local.py
    ...    ${root}/base.py
    ...    ${root}/remote.py

    ${python} =    Run Python Jiff    @{args}
    ${rust} =    Run Rust Jiff    @{args}

    Should Be Equal    ${python.stdout}    ${rust.stdout}
    ...    Python and Rust produced different inline three-way output
    Should Contain    ${python.stdout}    === 1: local.py vs 2: base.py ===
    Should Contain    ${python.stdout}    === 2: base.py vs 3: remote.py ===
    Should Contain    ${python.stdout}    Tonight at the Muppet Theatre
    Should Contain    ${python.stdout}    Performer("Miss Piggy", "diva")

Three-way Binary Renderers Agree
    [Documentation]    Checks binary input still shows both labelled comparisons.
    VAR    ${work_dir}    ${OUTPUT DIR}/jiff-system/${SUITE NAME}/${TEST NAME}
    VAR    ${local}    ${work_dir}/local.bin
    VAR    ${base}    ${work_dir}/base.bin
    VAR    ${remote}    ${work_dir}/remote.bin
    ${local_bytes} =    Evaluate    bytes([0, 1])
    ${base_bytes} =    Evaluate    bytes([0, 2])
    ${remote_bytes} =    Evaluate    bytes([0, 3])
    Create Binary File    ${local}    ${local_bytes}
    Create Binary File    ${base}    ${base_bytes}
    Create Binary File    ${remote}    ${remote_bytes}
    VAR    @{args}    --no-color    --no-pager    ${local}    ${base}    ${remote}

    ${python} =    Run Python Jiff    @{args}
    ${rust} =    Run Rust Jiff    @{args}

    Should Be Equal    ${python.stdout}    ${rust.stdout}
    ...    Python and Rust produced different binary three-way output
    Should Contain    ${python.stdout}    === 1: local.bin vs 2: base.bin ===
    Should Contain    ${python.stdout}    Binary files ${local} and ${base} differ
    Should Contain    ${python.stdout}    === 2: base.bin vs 3: remote.bin ===
    Should Contain    ${python.stdout}    Binary files ${base} and ${remote} differ

Three-way Colours Compose
    [Documentation]    Checks syntax colours remain visible under each three-way diff style.
    [Arguments]    ${runner}
    VAR    ${root}    ${CURDIR}/../../testcases/threeway/overlapping
    ${result} =    Run Keyword
    ...    ${runner}
    ...    --no-pager
    ...    ${root}/local.py
    ...    ${root}/base.py
    ...    ${root}/remote.py
    ${syntax_keyword} =    Evaluate    chr(27) + "[35m"
    ${add_highlight} =    Evaluate    chr(27) + "[42;30m"
    ${add_highlight_reordered} =    Evaluate    chr(27) + "[30;42m"
    ${remove_highlight} =    Evaluate    chr(27) + "[41;30m"
    ${remove_highlight_reordered} =    Evaluate    chr(27) + "[30;41m"
    ${overlap_highlight} =    Evaluate    chr(27) + "[43;30m"
    ${overlap_highlight_reordered} =    Evaluate    chr(27) + "[30;43m"

    Should Contain    ${result.stdout}    ${syntax_keyword}
    Should Contain Any
    ...    ${result.stdout}
    ...    ${add_highlight}
    ...    ${add_highlight_reordered}
    Should Contain Any
    ...    ${result.stdout}
    ...    ${remove_highlight}
    ...    ${remove_highlight_reordered}
    Should Contain Any
    ...    ${result.stdout}
    ...    ${overlap_highlight}
    ...    ${overlap_highlight_reordered}
