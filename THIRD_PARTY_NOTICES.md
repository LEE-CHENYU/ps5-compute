# Third-party notices

Original project code is copyright (c) 2026 Chenyu Li and licensed under the GNU General Public License, version 3 or (at your option) any later version. See [LICENSE](LICENSE).

The build fetches these dependencies separately; it does not vendor their source or binaries into this Git repository. Their own notices and any file-specific licenses remain authoritative.

| Project | Role | Pinned revision | Top-level license |
| --- | --- | --- | --- |
| [ps5-vulkan](https://github.com/mpereiraesaa/ps5-vulkan) | Experimental native compute backend | `e6d3c3f82f3c8a574e28c174b15b287f9c0ecc6d` | GPL-3.0 |
| [ps5-agc-gears](https://github.com/mpereiraesaa/ps5-agc-gears) | AGC declarations/stubs, native display/flip model | `1ae1f9182abd2770c131b97419034fb85173c2dc` | GPL-3.0 |
| [ps5-native-app-boilerplate](https://github.com/blackbearreloaded/ps5-native-app-boilerplate) | Native toolchain wrappers, application CRT, clean-room libc emitter, SELF packaging, framebuffer ABI | `37dd53602bdead63936f718004555ba10154be48` | GPL-3.0-or-later in source headers |
| [opengnm-psbc](https://github.com/mpereiraesaa/opengnm-psbc) | Mesa NIR/ACO-based shader compiler | `4fe7264a0cab9feb531a156e8a810b3e39cfe42c` | MIT; retain bundled Mesa notices |
| [OpenGNM](https://github.com/PS4-OpenGNM/opengnm) | GPU declarations and shader structures | `4b295ca54c82c83acf308d1c646a2dfa9ae57350` | MIT |
| [Vulkan-Headers](https://github.com/KhronosGroup/Vulkan-Headers) | Vulkan API declarations | `b51f6b865c18fc5b33990d12f75e8dfd672cede6` | See upstream LICENSES and per-file notices |
| [PS5 payload SDK](https://github.com/ps5-payload-dev/sdk) | Community SDK and runtime libraries | `v0.43` release archive; digest in `dependencies.py` | GPL-3.0-or-later tooling; runtime components have their own notices |

The dashboard's framebuffer ABI and flip ownership follow the native application foundation and Gears examples. The compute-only linkage and logger adapt the Vulkan backend to this standalone application. Upstream dependency files are not patched by this project.

## Bundled font

`assets/fonts/Barlow-Regular.ttf` is Barlow by The Barlow Project Authors, copyright 2017, distributed unchanged under SIL Open Font License 1.1. Its full license is [assets/fonts/OFL.txt](assets/fonts/OFL.txt). Source: [google/fonts at 6cdf01867df0813c2390f90dff7dc66c87f14cf7](https://github.com/google/fonts/tree/6cdf01867df0813c2390f90dff7dc66c87f14cf7/ofl/barlow). The build rasterizes this font for the console UI and icon.

Generated binaries are not distributed here. Any downstream binary distribution must also satisfy the applicable dependency licenses and corresponding-source requirements.
