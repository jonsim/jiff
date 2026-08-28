*** Settings ***
Library    Collections
Library    OperatingSystem
Library    Process

*** Keywords ***
Jiff Files
    [Documentation]    Runs both Jiff implementations for the given files and
    ...    checks their output against the expectation. Side-by-side cases use
    ...    the default mode; inline cases pass `--inline`.
    [Arguments]    ${left}    ${right}    ${expectation}    ${expect_side_by_side}=False
    VAR    ${base_dir}    ${CURDIR}/../..
    VAR    @{args}
    ...    ${base_dir}/testcases/${left}
    ...    ${base_dir}/testcases/${right}
    IF    not ${expect_side_by_side}
        Append To List    ${args}    --inline
    END

    ${skip_python} =    Get Variable Value  ${SKIP_PYTHON_TESTS}  ${False}
    IF    not ${skip_python}
        # Check the Python implementation's output.
        ${res} =    Run Python Jiff    @{args}
        ${expectation_str} =    Get File    ${base_dir}/testcases/${expectation}
        # Process strips one trailing newline from captured output. Match that
        # behaviour for hand-written fixtures which end in the usual newline.
        IF    len($expectation_str) and ord($expectation_str[-1]) == 10
            ${expectation_str} =    Set Variable    ${expectation_str}[0:-1]
        END
        Should Be Equal    ${res.stdout}    ${expectation_str}
        ...    Python implementation produced incorrect output
    END

    ${skip_rust} =    Get Variable Value  ${SKIP_RUST_TESTS}  ${False}
    IF    not ${skip_rust}
        # Check the Rust implementation's output.
        ${res} =    Run Rust Jiff    @{args}
        ${expectation_str} =    Get File    ${base_dir}/testcases/${expectation}
        IF    len($expectation_str) and ord($expectation_str[-1]) == 10
            ${expectation_str} =    Set Variable    ${expectation_str}[0:-1]
        END
        Should Be Equal    ${res.stdout}    ${expectation_str}
        ...    Rust implementation produced incorrect output
    END

Run Python Jiff
    [Documentation]    Runs the Python version of `jiff` with the given
    ...    arguments, checks for successful execution and returns the result
    ...    object.
    [Arguments]    @{args}
    Remove Environment Variable    JIFF_DEBUG
    VAR    @{cmd}    python3
    ...    ${CURDIR}/../../python/jiff.py
    ...    @{args}
    ${res} =    Run Process Check Output   @{cmd}
    RETURN    ${res}

Run Rust Jiff
    [Documentation]    Runs the Rust version of `jiff` with the given
    ...    arguments, checks for successful execution and returns the result
    ...    object.
    [Arguments]    @{args}
    Remove Environment Variable    JIFF_DEBUG
    VAR    @{cmd}    cargo
    ...    run
    ...    --manifest-path=${CURDIR}/../../Cargo.toml
    ...    --
    ...    @{args}
    ${res} =    Run Process Check Output    @{cmd}
    RETURN    ${res}

Run Python Jiff At Width
    [Documentation]    Runs Python with a terminal width supplied through `COLUMNS`.
    [Arguments]    ${width}    @{args}
    VAR    @{cmd}    python3
    ...    ${CURDIR}/../../python/jiff.py
    ...    @{args}
    ${res} =    Run Process Check Output At Width    ${width}    @{cmd}
    RETURN    ${res}

Run Rust Jiff At Width
    [Documentation]    Runs Rust with a terminal width supplied through `COLUMNS`.
    [Arguments]    ${width}    @{args}
    VAR    @{cmd}    cargo
    ...    run
    ...    --manifest-path=${CURDIR}/../../Cargo.toml
    ...    --
    ...    @{args}
    ${res} =    Run Process Check Output At Width    ${width}    @{cmd}
    RETURN    ${res}

Run Python Jiff With Colour
    [Documentation]    Runs the Python version with terminal colour forced on.
    [Arguments]    @{args}
    VAR    @{cmd}    python3
    ...    ${CURDIR}/../../python/jiff.py
    ...    @{args}
    ${res} =    Run Process Check Coloured Output    @{cmd}
    RETURN    ${res}

Run Rust Jiff With Colour
    [Documentation]    Runs the Rust version with terminal colour forced on.
    [Arguments]    @{args}
    VAR    @{cmd}    cargo
    ...    run
    ...    --manifest-path=${CURDIR}/../../Cargo.toml
    ...    --
    ...    @{args}
    ${res} =    Run Process Check Coloured Output    @{cmd}
    RETURN    ${res}

Run Python Jiff With Config
    [Documentation]    Runs the Python version with the given config and colour enabled.
    [Arguments]    ${config}    @{args}
    VAR    @{cmd}    python3
    ...    ${CURDIR}/../../python/jiff.py
    ...    @{args}
    ${res} =    Run Process Check Configured Output    ${config}    @{cmd}
    RETURN    ${res}

Run Rust Jiff With Config
    [Documentation]    Runs the Rust version with the given config and colour enabled.
    [Arguments]    ${config}    @{args}
    VAR    @{cmd}    cargo
    ...    run
    ...    --manifest-path=${CURDIR}/../../Cargo.toml
    ...    --
    ...    @{args}
    ${res} =    Run Process Check Configured Output    ${config}    @{cmd}
    RETURN    ${res}

Run Process Check Output
    [Documentation]    Runs a process with the given command and arguments,
    ...    checks for successful execution and returns the result object.
    [Arguments]    @{cmd}
    ${res} =    Run Process    @{cmd}    env:JIFF_CONFIG=${CURDIR}/default-config.toml
    Process Should Succeed    ${res}    @{cmd}
    RETURN    ${res}

Run Process Check Output At Width
    [Documentation]    Captures output with `COLUMNS` set to the requested width.
    [Arguments]    ${width}    @{cmd}
    ${res} =    Run Process    @{cmd}
    ...    env:COLUMNS=${width}
    ...    env:JIFF_CONFIG=${CURDIR}/default-config.toml
    Process Should Succeed    ${res}    @{cmd}
    RETURN    ${res}

Run Process Check Coloured Output
    [Documentation]    Runs a process as a colour-capable terminal at a stable width.
    [Arguments]    @{cmd}
    ${res} =    Run Process    @{cmd}
    ...    env:NO_COLOR=${EMPTY}
    ...    env:FORCE_COLOR=1
    ...    env:RICH_FORCE_TERMINAL=1
    ...    env:COLUMNS=120
    ...    env:JIFF_CONFIG=${CURDIR}/default-config.toml
    Process Should Succeed    ${res}    @{cmd}
    RETURN    ${res}

Run Process Check Configured Output
    [Documentation]    Runs a process with a specific config and terminal colour forced on.
    [Arguments]    ${config}    @{cmd}
    ${res} =    Run Process    @{cmd}
    ...    env:NO_COLOR=${EMPTY}
    ...    env:FORCE_COLOR=1
    ...    env:RICH_FORCE_TERMINAL=1
    ...    env:COLUMNS=120
    ...    env:JIFF_CONFIG=${config}
    Process Should Succeed    ${res}    @{cmd}
    RETURN    ${res}

Process Should Succeed
    [Documentation]    Reports a failed process with its command and captured output.
    [Arguments]    ${res}    @{cmd}
    IF    ${res.rc} != 0
        ${cmdline} =    Join Command Line    @{cmd}
        VAR    ${error}
        ...    Process failed with return code ${res.rc}
        ...    \n\nCommand:\n${cmdline}
        ...    \n\nStandard Output:\n${res.stdout}
        ...    \n\nStandard Error:\n${res.stderr}
        Fail    ${error}
    END
