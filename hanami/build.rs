/// Runs as the user, never asks for admin rights; written for Windows 10 and 11.
const MANIFEST: &str = r#"<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<assembly xmlns="urn:schemas-microsoft-com:asm.v1" manifestVersion="1.0">
  <trustInfo xmlns="urn:schemas-microsoft-com:asm.v3">
    <security>
      <requestedPrivileges>
        <requestedExecutionLevel level="asInvoker" uiAccess="false"/>
      </requestedPrivileges>
    </security>
  </trustInfo>
  <compatibility xmlns="urn:schemas-microsoft-com:compatibility.v1">
    <application>
      <supportedOS Id="{8e0f7a12-bfb3-4fe8-b9a5-48fd50a15a9a}"/>
    </application>
  </compatibility>
</assembly>
"#;

fn main() {
    slint_build::compile("ui/hanami.slint").unwrap();
    // The icon and details Explorer, the taskbar and Task Manager show for hanami.exe.
    if std::env::var("CARGO_CFG_TARGET_OS").as_deref() == Ok("windows") {
        let mut resource = winresource::WindowsResource::new();
        resource
            .set_icon("../packaging/windows/hanami.ico")
            .set("ProductName", "Hanami")
            .set("FileDescription", "Hanami game launcher")
            .set("CompanyName", "Hanami")
            .set("LegalCopyright", "Hanami contributors, GPL-3.0-or-later")
            .set("OriginalFilename", "hanami.exe")
            .set("InternalName", "hanami")
            .set("Comments", "https://hanami.lilygrove.dev")
            .set_manifest(MANIFEST);
        resource.compile().expect("couldn't add the Windows icon");
    }
}
