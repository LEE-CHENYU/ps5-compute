#ifndef ML_PS5LOG_H
#define ML_PS5LOG_H
enum { PS5LOG_INFO, PS5LOG_MARK, PS5LOG_ERR };
void ml_log_open(void);
void ps5log_printf(int level, const char *format, ...) __attribute__((format(printf, 2, 3)));
void ps5log_line(int level, const char *text);
void ps5log_close(const char *reason);
#endif
