fn main() {
    slint_build::compile("ui/hanami.slint").unwrap();
    // The icon and details Explorer, the taskbar and Task Manager show for hanami.exe.
    if std::env::var("CARGO_CFG_TARGET_OS").as_deref() == Ok("windows") {
        let mut resource = winresource::WindowsResource::new();
        resource
            .set_icon("../packaging/windows/hanami.ico")
            .set("ProductName", "Hanami")
            .set("FileDescription", "Hanami");
        resource.compile().expect("couldn't add the Windows icon");
    }
}
