*** Settings ***
Resource         jiff.resource
Test Template    Renderer Limits Unchanged Context


*** Test Cases ***    RUNNER             COLOUR_RUNNER
Python                 Run Python Jiff    Run Python Jiff With Colour
Rust                   Run Rust Jiff      Run Rust Jiff With Colour


*** Keywords ***
Renderer Limits Unchanged Context
    [Documentation]    Checks both option forms and preserves unlimited output by default.
    [Arguments]    ${runner}    ${colour_runner}
    VAR    ${work_dir}    ${OUTPUT DIR}/jiff-system/${SUITE NAME}/${TEST NAME}
    VAR    ${left}    ${work_dir}/context-left.txt
    VAR    ${right}    ${work_dir}/context-right.txt
    VAR    ${left_contents}     one\ntwo\nthree\nfour\nKermit\nsix\nseven\neight\nnine
    VAR    ${right_contents}    one\ntwo\nthree\nfour\nFozzie\nsix\nseven\neight\nnine
    Create Directory    ${work_dir}
    Create File    ${left}    ${left_contents}
    Create File    ${right}    ${right_contents}

    ${inline} =    Run Keyword
    ...    ${runner}
    ...    --inline
    ...    -U1
    ...    ${left}
    ...    ${right}
    Should Contain    ${inline.stdout}    ... 3 unchanged lines ...
    Should Contain    ${inline.stdout}    ${SPACE}${SPACE}four${\n}
    Should Contain    ${inline.stdout}    - Kermit${\n}
    Should Contain    ${inline.stdout}    + Fozzie${\n}
    Should Contain    ${inline.stdout}    ${SPACE}${SPACE}six${\n}
    Should Not Contain    ${inline.stdout}    ${SPACE}${SPACE}three${\n}
    Should Not Contain    ${inline.stdout}    ${SPACE}${SPACE}seven${\n}

    ${side_by_side} =    Run Keyword
    ...    ${runner}
    ...    --unified=0
    ...    ${left}
    ...    ${right}
    Should Contain    ${side_by_side.stdout}    ... 4 unchanged lines ...
    Should Contain    ${side_by_side.stdout}    5│ Kermit
    Should Contain    ${side_by_side.stdout}    5│ Fozzie
    Should Not Contain    ${side_by_side.stdout}    4│ four

    ${coloured_inline} =    Run Keyword
    ...    ${colour_runner}    --no-syntax    --inline    -U0    ${left}    ${right}
    ${coloured_side_by_side} =    Run Keyword
    ...    ${colour_runner}    --no-syntax    -U0    ${left}    ${right}
    Omission Uses Muted Colour    ${coloured_inline.stdout}
    Omission Uses Muted Colour    ${coloured_side_by_side.stdout}

    ${unlimited} =    Run Keyword    ${runner}    --inline    ${left}    ${right}
    Should Contain    ${unlimited.stdout}    ${SPACE}${SPACE}one${\n}
    Should Contain    ${unlimited.stdout}    ${SPACE}${SPACE}nine
    Should Not Contain    ${unlimited.stdout}    unchanged lines

Omission Uses Muted Colour
    [Documentation]    Checks context markers use the palette's quiet colour.
    [Arguments]    ${output}
    Output Should Contain ANSI Style    ${output}    foreground=bright_black
