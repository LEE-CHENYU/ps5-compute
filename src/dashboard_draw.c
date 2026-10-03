#include "dashboard.h"
#include "fonts.h"
#include <stdio.h>
#include <string.h>

// Framebuffer uses RGBA bytes. These colors are shared with the browser UI.
#define RGB(r,g,b) (0xff000000u|((b)<<16)|((g)<<8)|(r))
static const uint32_t background=RGB(20,34,53),panel=RGB(29,49,72),muted=RGB(156,180,202),
    white=RGB(240,244,248),blue=RGB(99,184,232),green=RGB(124,224,191),linecolor=RGB(48,71,95),
    red=RGB(255,139,146);
static void rect(uint32_t *p,int x,int y,int w,int h,uint32_t c) {
    for(int row=y;row<y+h&&row<1080;row++) if(row>=0)
        for(int col=x;col<x+w&&col<1920;col++) if(col>=0) p[row*1920+col]=c;
}
static void text(uint32_t *p,int x,int y,const char *str,const ml_font *font,uint32_t c) {
    for(;*str;str++) {
        unsigned code=(unsigned char)*str;if(code<32||code>126)code='?';
        const ml_glyph *g=&font->glyphs[code-32];
        for(unsigned row=0;row<g->height;row++) for(unsigned col=0;col<g->width;col++) {
            int px=x+(int)col,py=y+(int)row;if(px<0||py<0||px>=1920||py>=1080)continue;
            unsigned a=font->pixels[g->offset+row*g->width+col];if(!a)continue;
            uint32_t old=p[py*1920+px],value=0xff000000u;
            for(unsigned shift=0;shift<24;shift+=8)
                value|=((((c>>shift)&255)*a+((old>>shift)&255)*(255-a)+127)/255)<<shift;
            p[py*1920+px]=value;
        }
        x+=g->advance;
    }
}
void dashboard_draw(uint32_t *p,const ml_status *s) {
    rect(p,0,0,1920,1080,background);
    rect(p,72,70,7,60,blue);
    text(p,103,69,"PS5 / Compute",&font_40,white);
    text(p,1380,80,"Native GPU inference lab",&font_22,muted);
    rect(p,72,164,1776,2,linecolor);
    uint32_t accent=s->failed?red:s->running?blue:s->completed?green:blue;
    text(p,72,216,s->failed?"Run needs attention":s->running?"Computation in progress":s->completed?"Results verified":"Ready for a GPU task",&font_60,white);
    text(p,75,303,s->task[0]?s->task:"Matrix multiplication and a dense + ReLU layer",&font_28,muted);
    rect(p,72,375,1136,302,panel);
    text(p,108,409,s->phase,&font_40,accent);
    char value[128];
    snprintf(value,sizeof(value),"%u / %u GPU dispatches",s->completed,s->total);
    text(p,108,473,value,&font_28,white);
    rect(p,108,528,1064,12,linecolor);
    if(s->total) rect(p,108,528,(int)(1064ull*s->completed/s->total),12,accent);
    text(p,108,578,s->detail,&font_22,muted);
    text(p,1280,383,"Run monitoring",&font_28,white);
    snprintf(value,sizeof(value),"%.2f s",s->elapsed_ns/1e9);text(p,1280,438,value,&font_40,white);
    text(p,1510,451,"elapsed",&font_22,muted);
    snprintf(value,sizeof(value),"%.2f ms",s->last_ms);text(p,1280,501,value,&font_40,white);
    text(p,1510,514,"last dispatch + readback",&font_22,muted);
    snprintf(value,sizeof(value),"%.2f / %.2f MiB",s->gpu_bytes/1048576.0,s->peak_gpu_bytes/1048576.0);
    text(p,1280,564,value,&font_28,white);text(p,1280,606,"compute memory / peak",&font_22,muted);
    text(p,1280,646,"GPU utilization: not exposed",&font_22,muted);
    text(p,72,716,"Validation results",&font_28,white);
    snprintf(value,sizeof(value),"%u values checked    %u mismatches    %u guard errors",s->values,s->errors,s->guards);
    text(p,408,721,value,&font_22,s->errors||s->guards?red:muted);
    for(unsigned i=0;i<6;i++) {
        int x=72+(i%3)*600,y=775+(i/3)*76;
        rect(p,x,y,560,1,linecolor);
        snprintf(value,sizeof(value),"%s / input %u",i%2?"Dense + ReLU":"Matmul",i/2+1);
        text(p,x,y+20,value,&font_22,white);
        snprintf(value,sizeof(value),s->case_done[i]?"%.2f ms":"Waiting",s->case_ms[i]);
        text(p,x+389,y+20,value,&font_22,s->case_done[i]==2?red:s->case_done[i]?green:muted);
    }
    rect(p,72,953,1776,2,linecolor);
    text(p,72,991,"X  Run once     Square  Repeat 20 times     Options  Close when idle",&font_22,white);
    if(s->cpu_temp<0||s->soc_temp<0)snprintf(value,sizeof(value),"%s   Temperature unavailable",s->controller?"Controller connected":"Controller unavailable");
    else snprintf(value,sizeof(value),"%s   CPU %d C   SoC %d C",s->controller?"Controller connected":"Controller unavailable",s->cpu_temp,s->soc_temp);
    text(p,1240,993,value,&font_22,muted);
}
