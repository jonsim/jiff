*** Settings ***
Resource    jiff.resource
Test Template    Renderer Uses One Colour Palette

*** Test Cases ***    RUNNER
Python Colouring      Run Python Jiff With Colour
Rust Colouring        Run Rust Jiff With Colour

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
