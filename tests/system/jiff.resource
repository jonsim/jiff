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
        Should Be Equal    ${res.stdout}    ${expectation_str}
        ...    Python implementation produced incorrect output
    END

    ${skip_rust} =    Get Variable Value  ${SKIP_RUST_TESTS}  ${False}
    IF    not ${skip_rust}
        # Check the Rust implementation's output.
        ${res} =    Run Rust Jiff    @{args}
        ${expectation_str} =    Get File    ${base_dir}/testcases/${expectation}
        Should Be Equal    ${res.stdout}    ${expectation_str}
        ...    Rust implementation produced incorrect output
    END


Jiff Strings
    [Documentation]    Writes the left and right strings to temporary files,
    ...    then runs the Jiff Files keyword with those files and the
    ...    expectation.
    [Arguments]    ${left}    ${right}    ${expectation}
    Create File    ${TEMPDIR}/left.txt           ${left}
    Create File    ${TEMPDIR}/right.txt          ${right}
    Create File    ${TEMPDIR}/expectation.txt    ${expectation}
    Jiff Files     ${TEMPDIR}/left.txt
    ...            ${TEMPDIR}/right.txt
    ...            ${TEMPDIR}/expectation.txt

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

Run Process Check Output
    [Documentation]    Runs a process with the given command and arguments,
    ...    checks for successful execution and returns the result object.
    [Arguments]    @{cmd}
    ${res} =    Run Process    @{cmd}
    IF    ${res.rc} != 0
        ${cmdline} =    Join Command Line    @{cmd}
        VAR    ${error}
        ...    Process failed with return code ${res.rc}
        ...    \n\nCommand:\n${cmdline}
        ...    \n\nStandard Output:\n${res.stdout}
        ...    \n\nStandard Error:\n${res.stderr}
        Fail    ${error}
    END
    RETURN    ${res}
