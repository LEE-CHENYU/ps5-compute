#ifndef ML_DASHBOARD_H
#define ML_DASHBOARD_H
#include <stdint.h>
typedef struct {
    char phase[32], task[80], detail[180], build[24];
    unsigned running, failed, completed, total, values, errors, guards, inputs;
    unsigned suite, suites, sequence, controller;
    uint64_t started_ns, elapsed_ns, gpu_bytes, peak_gpu_bytes;
    double last_ms, case_ms[6];
    unsigned case_done[6];
    int cpu_temp, soc_temp;
} ml_status;
void dashboard_log(const char *line);
void dashboard_snapshot(ml_status *out);
void dashboard_draw(uint32_t *pixels, const ml_status *s);
int ml_run(void);
#endif
