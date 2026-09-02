*** Settings ***
Resource    jiff.resource

*** Test Cases ***
Python Colouring
    [Template]    Renderer Uses One Colour Palette
    Run Python Jiff With Colour

Rust Colouring
    [Template]    Renderer Uses One Colour Palette
    Run Rust Jiff With Colour

Python ANSI256
    [Template]    Renderer Uses ANSI256 When Supported
    python3    ${CURDIR}/../../python/jiff.py

Rust ANSI256
    [Template]    Renderer Uses ANSI256 When Supported
    cargo    run    --quiet    --manifest-path=${CURDIR}/../../Cargo.toml    --

*** Keywords ***
Renderer Uses One Colour Palette
    [Documentation]    Checks inline and side-by-side output use the same diff colours.
    [Arguments]    ${runner}
    VAR    ${base_dir}    ${CURDIR}/../..
    VAR    ${first}    ${base_dir}/testcases/minimal/02.txt
    VAR    ${first_hello}    ${base_dir}/testcases/minimal/03.txt

    ${inline_addition} =    Run Keyword
    ...    ${runner}    --inline    ${first}    ${first_hello}
    ${inline_removal} =    Run Keyword
    ...    ${runner}    --inline    ${first_hello}    ${first}
    Outputs Use Diff Colours    ${inline_addition.stdout}    ${inline_removal.stdout}

    ${side_by_side_addition} =    Run Keyword
    ...    ${runner}    ${first}    ${first_hello}
    ${side_by_side_removal} =    Run Keyword
    ...    ${runner}    ${first_hello}    ${first}
    Outputs Use Diff Colours
    ...    ${side_by_side_addition.stdout}
    ...    ${side_by_side_removal.stdout}

    ${inline_plain} =    Run Keyword
    ...    ${runner}    --no-color    --inline    ${first}    ${first_hello}
    ${side_by_side_plain} =    Run Keyword
    ...    ${runner}    --no-color    ${first}    ${first_hello}
    ${sgr} =    Evaluate    chr(27) + "["
    Should Not Contain    ${inline_plain.stdout}    ${sgr}
    Should Not Contain    ${side_by_side_plain.stdout}    ${sgr}

Outputs Use Diff Colours
    [Documentation]    Checks normal and highlighted additions and removals.
    [Arguments]    ${addition_output}    ${removal_output}
    Output Should Contain ANSI Style    ${addition_output}    foreground=red
    Output Should Contain ANSI Style    ${addition_output}    foreground=green
    Output Should Contain ANSI Style
    ...    ${addition_output}
    ...    foreground=black
    ...    background=green
    Output Should Contain ANSI Style    ${removal_output}    foreground=red
    Output Should Contain ANSI Style    ${removal_output}    foreground=green
    Output Should Contain ANSI Style
    ...    ${removal_output}
    ...    foreground=black
    ...    background=red

Renderer Uses ANSI256 When Supported
    [Documentation]    Checks ANSI256, true-colour and ANSI16 terminal profiles.
    [Arguments]    @{command}
    VAR    ${config}    ${CURDIR}/ansi256-config.toml
    VAR    ${first}    ${CURDIR}/../../testcases/minimal/02.txt
    VAR    ${changed}    ${CURDIR}/../../testcases/minimal/03.txt
    ${ansi256} =    Run Process Check Configured Output For Terminal
    ...    ${config}    xterm-256color    ${EMPTY}
    ...    @{command}    --inline    ${first}    ${changed}
    Output Should Contain ANSI Style    ${ansi256.stdout}    foreground=color(114)

    ${true_colour} =    Run Process Check Configured Output For Terminal
    ...    ${config}    xterm    truecolor
    ...    @{command}    --inline    ${first}    ${changed}
    Output Should Contain ANSI Style    ${true_colour.stdout}    foreground=color(114)

    ${ansi16} =    Run Process Check Configured Output For Terminal
    ...    ${config}    xterm    ${EMPTY}
    ...    @{command}    --inline    ${first}    ${changed}
    Output Should Contain ANSI Style    ${ansi16.stdout}    foreground=green
    Output Should Not Contain ANSI Style    ${ansi16.stdout}    foreground=color(114)

    ${git_diff} =    Run External Diff For Terminal
    ...    ${config}    xterm-256color
    ...    @{command}    --git-external-diff
    ...    muppets.txt    ${first}    old    100644    ${changed}    new    100644
    Output Should Contain ANSI Style    ${git_diff.stdout}    foreground=color(114)
