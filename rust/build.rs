use std::path::PathBuf;

fn main() {
    let manifest_dir = PathBuf::from(
        std::env::var("CARGO_MANIFEST_DIR").expect("CARGO_MANIFEST_DIR is set by cargo"),
    );
    let repo_root = manifest_dir
        .parent()
        .expect("rust crate lives in a subdirectory of the repository root")
        .to_path_buf();
    let cadical_src = repo_root.join("vendor").join("cadical").join("src");
    let cadical_build = repo_root.join("vendor").join("cadical").join("build");
    let shim = repo_root.join("vendor").join("cadical_shim.cpp");

    cc::Build::new()
        .cpp(true)
        .file(&shim)
        .include(&cadical_src)
        .flag_if_supported("-O2")
        .flag_if_supported("-fPIC")
        .flag_if_supported("-std=c++17")
        .compile("cadical_shim");

    println!("cargo:rustc-link-search=native={}", cadical_build.display());
    println!("cargo:rustc-link-lib=static=cadical");
    println!("cargo:rustc-link-lib=dylib=stdc++");

    println!("cargo:rerun-if-changed={}", shim.display());
    println!(
        "cargo:rerun-if-changed={}",
        cadical_build.join("libcadical.a").display()
    );
}
