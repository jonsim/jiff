mod diff;

use std::fs;
use std::process;
use clap::{Arg, App};

fn read_file_or_die(path: &str) -> String {
    match fs::read_to_string(path) {
        Ok(content) => content,
        Err(ref error)  => {
            eprintln!("Could not read {}: {}", path, error);
            process::exit(1);
        },
    }
}

fn main() {
    // Handle command line.
    let matches = App::new("jiff")
                    .version("1.0")
                    .about("Colored diff tool")
                    .arg(Arg::with_name("git-diff")
                        .short("g")
                        .long("git-diff")
                        .help("Enable git diff mode"))
                    .arg(Arg::with_name("side-by-side")
                        .short("s")
                        .long("side-by-side")
                        .help("Enable side-by-side diffing"))
                    .arg(Arg::with_name("no-color")
                        .long("no-color")
                        .help("Disables colorization of the output"))
                    .arg(Arg::with_name("file1")
                        .required(true)
                        .help("Left file"))
                    .arg(Arg::with_name("file2")
                        .required(true)
                        .help("Right file"))
                    .get_matches();
    let lpath = matches.value_of("file1").expect("file1 is required");
    let rpath = matches.value_of("file2").expect("file2 is required");
    let lfile = read_file_or_die(lpath);
    let rfile = read_file_or_die(rpath);
    //println!("lpath: {}\n{}\nrpath: {}\n{}\n", lpath, lfile, rpath, rfile);

    // Calculate the changeset.
    let diffs = diff::calculate_diff(&lfile, &rfile);
    diff::print_diffs(&diffs, true);

    // Print the changeset.
    if matches.is_present("side-by-side") {
        //print_diff_side_by_side(&changeset);
    } else {
        //print_diff(&changeset);
    }
}
