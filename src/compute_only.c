#include "wsi_present_backend.h"
// This title has no display/swapchain backend. GPU compute uses the unchanged
// upstream native AGC submission path; no compute operation is emulated here.
VkBool32 ps5vk_wsi_present_available(void) { return VK_FALSE; }
