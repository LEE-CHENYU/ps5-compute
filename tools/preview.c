#include "dashboard.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
int main(int argc,char **argv){
    ml_status s={.phase="Ready",.task="Matrix multiplication and a dense + ReLU layer",
        .detail="Choose a task below. The browser dashboard can start runs too.",.total=6,.controller=0,.cpu_temp=-1,.soc_temp=-1};
    if(argc>1&&strcmp(argv[1],"passed")==0){
        snprintf(s.phase,sizeof(s.phase),"Passed");s.completed=6;s.values=546;s.elapsed_ns=1250000000;s.last_ms=9.26;s.peak_gpu_bytes=262144;
        snprintf(s.detail,sizeof(s.detail),"Every output matched. Inputs and guards unchanged. Compute memory released.");
        for(unsigned i=0;i<6;i++){s.case_done[i]=1;s.case_ms[i]=9.2+i/10.0;}
    }
    uint32_t *p=calloc(1920*1080,4);dashboard_draw(p,&s);
    printf("P6\n1920 1080\n255\n");
    for(unsigned i=0;i<1920*1080;i++){putchar(p[i]&255);putchar((p[i]>>8)&255);putchar((p[i]>>16)&255);}
    free(p);return 0;
}
