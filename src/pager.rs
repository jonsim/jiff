use std::env;
use std::io::{self, IsTerminal, Write};
use std::process::{Command, Stdio};
use unicode_width::UnicodeWidthStr;

const DEFAULT_TERMINAL_WIDTH: usize = 80;
const DEFAULT_TERMINAL_HEIGHT: usize = 24;
const TAB_WIDTH: usize = 4;

pub(super) fn display(output: &str, no_pager: bool) -> io::Result<()> {
    let stdout = io::stdout();
    let is_terminal = stdout.is_terminal();
    let terminal_size =
        term_size::dimensions_stdout().unwrap_or((DEFAULT_TERMINAL_WIDTH, DEFAULT_TERMINAL_HEIGHT));

    if should_page(output, no_pager, is_terminal, terminal_size) {
        return run_pager(output);
    }

    match stdout.lock().write_all(output.as_bytes()) {
        // `head` closes stdout once it has enough. That's normal, just like
        // quitting the pager early.
        Err(error) if error.kind() == io::ErrorKind::BrokenPipe => Ok(()),
        result => result,
    }
}

fn should_page(
    output: &str,
    no_pager: bool,
    is_terminal: bool,
    terminal_size: (usize, usize),
) -> bool {
    if no_pager || !is_terminal {
        return false;
    }

    output_height(output, terminal_size.0.max(1)) > terminal_size.1.max(1)
}

fn output_height(output: &str, terminal_width: usize) -> usize {
    let plain = strip_ansi_sequences(output);
    plain
        .lines()
        .map(|line| {
            let width = display_width(line);
            width.saturating_sub(1) / terminal_width + 1
        })
        .sum()
}

fn display_width(line: &str) -> usize {
    let mut width = 0;
    let mut parts = line.split('\t').peekable();
    while let Some(part) = parts.next() {
        width += part.width();
        if parts.peek().is_some() {
            width += TAB_WIDTH - width % TAB_WIDTH;
        }
    }
    width
}

fn strip_ansi_sequences(output: &str) -> String {
    let mut plain = String::with_capacity(output.len());
    let mut chars = output.chars().peekable();

    while let Some(character) = chars.next() {
        if character == '\x1b' && chars.next_if_eq(&'[').is_some() {
            // CSI sequences end at their first byte in the range @ through ~.
            // Jiff currently emits SGR colour sequences, but accepting the
            // complete range keeps terminal controls out of width calculations.
            for control in chars.by_ref() {
                if ('@'..='~').contains(&control) {
                    break;
                }
            }
        } else {
            plain.push(character);
        }
    }

    plain
}

fn run_pager(output: &str) -> io::Result<()> {
    let pager = env::var("PAGER")
        .ok()
        .filter(|pager| !pager.trim().is_empty())
        .unwrap_or_else(|| "less".to_string());
    let mut command = Command::new("sh");
    command.arg("-c").arg(pager).stdin(Stdio::piped());

    // These are the usual Jiff defaults for less: keep colour, quit if our size
    // check was conservative, and leave the output on screen.
    if env::var_os("LESS").is_none() {
        command.env("LESS", "FRX");
    }

    let mut child = command.spawn()?;
    let write_result = child
        .stdin
        .take()
        .expect("piped pager input is available")
        .write_all(output.as_bytes());
    let status = child.wait()?;

    if let Err(error) = write_result {
        // Quitting the pager closes its input while Jiff may still be writing.
        // That's normal, not a failed diff.
        if error.kind() != io::ErrorKind::BrokenPipe {
            return Err(error);
        }
    }

    if status.success() {
        Ok(())
    } else {
        Err(io::Error::other(format!(
            "pager exited with status {status}"
        )))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn output_that_fits_exactly_does_not_page() {
        // An exact fit is still visible without taking over the terminal.
        let output = "Kermit\nFozzie\n";

        assert!(!should_page(output, false, true, (80, 2)));
    }

    #[test]
    fn output_taller_than_the_terminal_pages() {
        let output = "Kermit\nFozzie\nGonzo\n";

        assert!(should_page(output, false, true, (80, 2)));
    }

    #[test]
    fn wrapped_lines_count_towards_terminal_height() {
        let output = "Kermit the Frog\n";

        assert!(should_page(output, false, true, (6, 2)));
    }

    #[test]
    fn ansi_colours_do_not_make_lines_look_wider() {
        let output = "\x1b[31mKermit\x1b[0m\n";

        assert!(!should_page(output, false, true, (6, 1)));
    }

    #[test]
    fn no_pager_overrides_a_tall_output() {
        let output = "Kermit\nFozzie\nGonzo\n";

        assert!(!should_page(output, true, true, (80, 2)));
    }

    #[test]
    fn redirected_output_never_pages() {
        let output = "Kermit\nFozzie\nGonzo\n";

        assert!(!should_page(output, false, false, (80, 2)));
    }
}
