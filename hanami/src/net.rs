//! Hanami's only trips online: small text files from GitHub, at most once a
//! day, and never when `online = false`.

use std::time::Duration;

/// The text at `url`, or why it couldn't be fetched.
pub fn get(url: &str) -> Result<String, String> {
    let agent: ureq::Agent = ureq::Agent::config_builder()
        .timeout_global(Some(Duration::from_secs(10)))
        .user_agent(concat!("hanami/", env!("CARGO_PKG_VERSION")))
        .build()
        .into();
    let mut response = agent.get(url).call().map_err(|error| error.to_string())?;
    response.body_mut().read_to_string().map_err(|error| error.to_string())
}
