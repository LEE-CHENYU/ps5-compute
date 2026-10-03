#include "ps5log.h"
#include "build_id.h"
#if ML_DASHBOARD
#include "dashboard.h"
#endif
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include <fcntl.h>

// Local durable log replaces the upstream private telemetry dependency.
// The host retrieves this file over FTP; no workstation address is embedded.
static int file = -1;
void ml_log_open(void) {
    file = open("/data/ps5-ml/latest.log", O_WRONLY | O_CREAT | O_TRUNC, 0666);
}
void ps5log_printf(int level, const char *format, ...) {
    (void)level;
    char line[2048];
    va_list ap; va_start(ap, format);
    int n = vsnprintf(line, sizeof(line)-2, format, ap); va_end(ap);
    if (n < 0) return;
    size_t size = (size_t)n < sizeof(line)-2 ? (size_t)n : sizeof(line)-2;
#if ML_DASHBOARD
    line[size]='\0';dashboard_log(line);
#endif
    line[size++] = '\n';
    if (file >= 0) { (void)write(file, line, size); (void)fsync(file); }
}
void ps5log_line(int level, const char *text) { ps5log_printf(level, "%s", text); }
void ps5log_close(const char *reason) {
    ps5log_printf(PS5LOG_MARK, "ML_LOG_END reason=%s", reason);
    if (file >= 0) close(file);
    file = -1;
}
