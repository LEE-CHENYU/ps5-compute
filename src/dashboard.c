#include "dashboard.h"
#include "ps5log.h"
#include "build_id.h"
#include "ps5_platform.h"
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include <fcntl.h>
#include <sys/stat.h>

extern int sceVideoOutSubmitFlip(int,int,unsigned,int64_t);
extern int sceSystemServiceHideSplashScreen(void);
extern int sceKernelGetCpuTemperature(int *);
extern int sceKernelGetSocSensorTemperature(int,int *);
extern int sceUserServiceGetInitialUser(int32_t *);
static pthread_mutex_t lock=PTHREAD_MUTEX_INITIALIZER;
static int close_requested;
static ml_status status={.phase="Ready",.task="Matrix multiplication and a dense + ReLU layer",
    .detail="Choose a task below. The browser dashboard can start runs too.",.build=ML_BUILD_ID,.total=6};
static uint64_t monotonic(void){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return (uint64_t)t.tv_sec*1000000000ull+t.tv_nsec;}
void dashboard_snapshot(ml_status *out){pthread_mutex_lock(&lock);*out=status;pthread_mutex_unlock(&lock);if(out->running)out->elapsed_ns=monotonic()-out->started_ns;}
void dashboard_log(const char *line){
    pthread_mutex_lock(&lock);
    unsigned round,kind,checked,errors,guards,inputs;unsigned long long elapsed,bytes;
    if(strncmp(line,"ML_PHASE phase=",15)==0){
        char phase[32];if(sscanf(line,"ML_PHASE phase=%31s",phase)==1)snprintf(status.phase,sizeof(status.phase),"%s",phase);
    } else if(sscanf(line,"ML_RESULT round=%u kind=%u checked=%u errors=%u guard_errors=%u input_errors=%u max_abs_error=%*f submit_wait_readback_ns=%llu",&round,&kind,&checked,&errors,&guards,&inputs,&elapsed)==7){
        status.completed++;status.values+=checked;status.errors+=errors;status.guards+=guards;status.inputs+=inputs;
        status.last_ms=elapsed/1e6;
        if(round<3&&kind<2){status.case_ms[round*2+kind]=status.last_ms;status.case_done[round*2+kind]=errors||guards||inputs?2:1;}
        snprintf(status.detail,sizeof(status.detail),"Suite %u of %u. Outputs checked against an independent CPU reference.",status.suite,status.suites);
    } else if(sscanf(line,"PS5VK_MEMORY_ALLOC requested=%*u mapped=%llu",&bytes)==1){
        status.gpu_bytes+=bytes;if(status.gpu_bytes>status.peak_gpu_bytes)status.peak_gpu_bytes=status.gpu_bytes;
    } else if(sscanf(line,"PS5VK_MEMORY_RELEASE mapped=%llu",&bytes)==1){
        status.gpu_bytes=status.gpu_bytes>=bytes?status.gpu_bytes-bytes:0;
    } else if(strstr(line,"ML_FAIL")||strstr(line,"_RETAIN")){
        status.failed=1;snprintf(status.phase,sizeof(status.phase),"Failed");
        snprintf(status.detail,sizeof(status.detail),"%.165s",line);
    }
    status.sequence++;pthread_mutex_unlock(&lock);
}
static void *worker(void *unused){
    (void)unused;
    unsigned suites;pthread_mutex_lock(&lock);suites=status.suites;pthread_mutex_unlock(&lock);
    for(unsigned i=0;i<suites;i++){
        pthread_mutex_lock(&lock);status.suite=i+1;pthread_mutex_unlock(&lock);
        ml_run();
    }
    pthread_mutex_lock(&lock);status.running=0;status.elapsed_ns=monotonic()-status.started_ns;
    snprintf(status.phase,sizeof(status.phase),"Passed");snprintf(status.detail,sizeof(status.detail),"Every output matched. Inputs and guards unchanged. Compute memory released.");
    pthread_mutex_unlock(&lock);
    ps5log_line(PS5LOG_MARK,"DASHBOARD_TASK_COMPLETE");return NULL;
}
static void start_run(unsigned suites){
    pthread_mutex_lock(&lock);
    if(status.running||status.failed){pthread_mutex_unlock(&lock);return;}
    unsigned controller=status.controller;int cpu=status.cpu_temp,soc=status.soc_temp;
    memset(&status,0,sizeof(status));status.running=1;status.suites=suites;status.total=suites*6;status.started_ns=monotonic();
    status.controller=controller;status.cpu_temp=cpu;status.soc_temp=soc;
    snprintf(status.build,sizeof(status.build),"%s",ML_BUILD_ID);
    snprintf(status.phase,sizeof(status.phase),"Starting");snprintf(status.task,sizeof(status.task),suites==1?"FP32 kernel validation":"Repeated validation / 20 suites");
    snprintf(status.detail,sizeof(status.detail),"Opening the native Vulkan compute device.");pthread_mutex_unlock(&lock);
    pthread_t thread;int rc=pthread_create(&thread,NULL,worker,NULL);
    if(rc){pthread_mutex_lock(&lock);status.running=0;status.failed=1;snprintf(status.phase,sizeof(status.phase),"Worker failed");pthread_mutex_unlock(&lock);}
    else pthread_detach(thread);
}
static void json_string(FILE *f,const char *s){fputc('"',f);for(;*s;s++){unsigned c=(unsigned char)*s;if(c=='"'||c=='\\')fputc('\\',f);if(c>=32)fputc(c,f);}fputc('"',f);}
static void write_status(const ml_status *s){
    FILE *f=fopen("/data/ps5-ml/status.next","w");if(!f)return;
    fprintf(f,"{\"schema\":1,\"pid\":%d,\"heartbeat\":%lld,\"build\":",(int)getpid(),(long long)time(NULL));json_string(f,s->build);
    fprintf(f,",\"run_id\":%llu",(unsigned long long)s->started_ns);
    fprintf(f,",\"phase\":");json_string(f,s->phase);fprintf(f,",\"task\":");json_string(f,s->task);fprintf(f,",\"detail\":");json_string(f,s->detail);
    fprintf(f,",\"running\":%s,\"failed\":%s,\"completed\":%u,\"total\":%u,\"values\":%u,\"errors\":%u,\"guard_errors\":%u,\"input_errors\":%u,\"elapsed_s\":%.3f,\"last_ms\":%.4f,\"gpu_bytes\":%llu,\"peak_gpu_bytes\":%llu,\"display_bytes\":33554432,\"gpu_utilization\":null,\"cpu_c\":%d,\"soc_c\":%d,\"controller\":%s,\"cases\":[",
        s->running?"true":"false",s->failed?"true":"false",s->completed,s->total,s->values,s->errors,s->guards,s->inputs,s->elapsed_ns/1e9,s->last_ms,
        (unsigned long long)s->gpu_bytes,(unsigned long long)s->peak_gpu_bytes,s->cpu_temp,s->soc_temp,s->controller?"true":"false");
    for(unsigned i=0;i<6;i++)fprintf(f,"%s{\"round\":%u,\"kind\":%u,\"done\":%s,\"ok\":%s,\"ms\":%.4f}",i?",":"",i/2,i%2,s->case_done[i]?"true":"false",s->case_done[i]==1?"true":"false",s->case_ms[i]);
    fputs("]}\n",f);fclose(f);rename("/data/ps5-ml/status.next","/data/ps5-ml/status.json");
}
static void read_command(void){
    FILE *f=fopen("/data/ps5-ml/command.txt","r");if(!f)return;
    char command[24]={0};(void)fgets(command,sizeof(command),f);fclose(f);unlink("/data/ps5-ml/command.txt");
    if(strcmp(command,"once\n")==0)start_run(1);
    else if(strcmp(command,"repeat\n")==0)start_run(20);
    else if(strcmp(command,"close\n")==0){ml_status s;dashboard_snapshot(&s);if(!s.running)close_requested=1;}
}
static void cache(void *address,size_t bytes){
    for(uintptr_t p=(uintptr_t)address;p<(uintptr_t)address+bytes;p+=64)__asm__ volatile("clflush (%0)"::"r"(p):"memory");
    __asm__ volatile("mfence":::"memory");
}
int main(void){
    ml_log_open();ps5log_printf(PS5LOG_MARK,"DASHBOARD_BOOT build=%s pid=%d",ML_BUILD_ID,(int)getpid());
    int video=sceVideoOutOpen(0xff,0,0,NULL);if(video<0){ps5log_printf(PS5LOG_ERR,"DASHBOARD_FAIL video=%d",video);_exit(1);}
    int64_t physical=0;void *mapped=NULL;const size_t frame_bytes=0x1000000,bytes=0x2000000;
    int rc=sceKernelAllocateMainDirectMemory(bytes,0x200000,3,&physical);
    if(!rc)rc=sceKernelMapDirectMemory(&mapped,bytes,0x33,0,physical,0x200000);
    if(rc){ps5log_printf(PS5LOG_ERR,"DASHBOARD_FAIL memory=%d",rc);_exit(1);}
    void *queue=NULL;rc=sceKernelCreateEqueue(&queue,"ps5-ml-display");if(!rc)rc=sceVideoOutAddFlipEvent(queue,video,NULL);
    struct ps5_video_buffer buffers[2]={{mapped,NULL,NULL,NULL},{(char *)mapped+frame_bytes,NULL,NULL,NULL}};
    struct ps5_video_attribute attribute={{0}};
    sceVideoOutSetBufferAttribute2(&attribute,0x8000000022000000ull,0,1920,1080,0,0,0);
    if(!rc)rc=sceVideoOutRegisterBuffers2(video,0,0,buffers,2,&attribute,0,NULL);
    if(rc){ps5log_printf(PS5LOG_ERR,"DASHBOARD_FAIL setup=%d",rc);_exit(1);}
    sceVideoOutSetFlipRate(video,0);sceSystemServiceHideSplashScreen();
    int32_t user=-1;int pad=-1;
    int user_rc=sceUserServiceInitialize(NULL),pad_rc=scePadInit();
    ps5log_printf(PS5LOG_MARK,"DASHBOARD_INPUT init_user=0x%x init_pad=0x%x",user_rc,pad_rc);
    uint32_t previous=0;unsigned slot=0;int64_t token=1;uint64_t heartbeat=0;
    for(;;){
        struct ps5_pad_data input={0};uint32_t pressed=0;
        if(pad>=0&&!scePadReadState(pad,&input)&&input.connected&&!(input.buttons&0x80000000u)){pressed=input.buttons&~previous;previous=input.buttons;}
        pthread_mutex_lock(&lock);status.controller=input.connected!=0;pthread_mutex_unlock(&lock);
        if(pressed&0x4000)start_run(1);if(pressed&0x8000)start_run(20);
        read_command();ml_status view;dashboard_snapshot(&view);
        if(((pressed&0x8)||close_requested)&&!view.running)break;
        if(monotonic()-heartbeat>1000000000ull){
            if(pad<0){
                int user_result=sceUserServiceGetForegroundUser(&user);
                if(user_result)user_result=sceUserServiceGetInitialUser(&user);
                if(!user_result)pad=scePadOpen(user,0,0,NULL);
                ps5log_printf(PS5LOG_MARK,"DASHBOARD_INPUT user_result=0x%x pad_open=0x%x",user_result,pad);
            }
            int cpu=-1,soc=-1;sceKernelGetCpuTemperature(&cpu);sceKernelGetSocSensorTemperature(0,&soc);
            pthread_mutex_lock(&lock);status.cpu_temp=cpu;status.soc_temp=soc;pthread_mutex_unlock(&lock);
            dashboard_snapshot(&view);write_status(&view);heartbeat=monotonic();
        }
        uint32_t *pixels=(void *)((char *)mapped+slot*frame_bytes);dashboard_draw(pixels,&view);cache(pixels,1920*1080*4);
        rc=sceVideoOutSubmitFlip(video,(int)slot,1,token);
        if(rc){ps5log_printf(PS5LOG_ERR,"DASHBOARD_FAIL flip=%d",rc);break;}
        // Wait for the exact flip token before reusing the previous scanout.
        int seen=0;for(unsigned tries=0;tries<10&&!seen;tries++){
            unsigned char event[64]={0};int count=0;unsigned timeout=100000;
            int er=sceKernelWaitEqueue(queue,event,1,&count,&timeout);int64_t observed=0;
            if(!er&&count==1&&!sceVideoOutGetEventData(event,&observed)&&observed==token)seen=1;
        }
        if(!seen){ps5log_line(PS5LOG_ERR,"DASHBOARD_FAIL flip-timeout");for(;;)sleep(1);}
        if(token==1)ps5log_line(PS5LOG_MARK,"DASHBOARD_READY display=1920x1080 flip-confirmed=1");
        slot^=1;token++;usleep(150000);
    }
    if(pad>=0)scePadClose(pad);
    sceVideoOutDeleteFlipEvent(queue,video);sceKernelDeleteEqueue(queue);sceVideoOutClose(video);
    sceKernelMunmap(mapped,bytes);sceKernelReleaseDirectMemory(physical,bytes);
    unlink("/data/ps5-ml/status.json");ps5log_close("dashboard-closed");_exit(0);
}
