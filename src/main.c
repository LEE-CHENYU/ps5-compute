#include <vulkan/vulkan_core.h>
#include "ps5log.h"
#include "shaders.h"
#include "build_id.h"
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <math.h>
#include <time.h>
#include <unistd.h>

enum { M=7, K=16, N=13, ELEMENTS=M*N, WORDS=4096, FIRST=64 };
static void fail(const char *operation, int rc) {
    ps5log_printf(PS5LOG_ERR, "ML_FAIL operation=%s rc=%d", operation, rc);
    ps5log_close("failure-retained");
    // A failed queue can still own GPU memory. Leave it to title teardown.
    for (;;) sleep(1);
}
#define CHECK(call) do { VkResult r=(call); if(r!=VK_SUCCESS) fail(#call,r); } while(0)
static uint64_t ns(void) {
    struct timespec ts; clock_gettime(CLOCK_MONOTONIC,&ts);
    return (uint64_t)ts.tv_sec*1000000000ull+ts.tv_nsec;
}
static void barrier(VkCommandBuffer cb, VkPipelineStageFlags src, VkPipelineStageFlags dst,
                    VkAccessFlags from, VkAccessFlags to) {
    VkMemoryBarrier b={.sType=VK_STRUCTURE_TYPE_MEMORY_BARRIER,.srcAccessMask=from,.dstAccessMask=to};
    vkCmdPipelineBarrier(cb,src,dst,0,1,&b,0,NULL,0,NULL);
}
static float xvalue(unsigned i,unsigned round) { return ((int)((i*7+round*3)%19)-9)/8.0f; }
static float wvalue(unsigned i,unsigned round) { return ((int)((i*11+round*5)%23)-11)/8.0f; }
static float bias(unsigned i,unsigned round) { return ((int)((i*3+round)%7)-3)/4.0f; }

int ml_run(void) {
#if !ML_DASHBOARD
    ml_log_open();
#endif
    ps5log_printf(PS5LOG_MARK,"ML_BOOT build=%s pid=%d backend=native-ps5-vulkan preflight=%d",ML_BUILD_ID,(int)getpid(),ML_PREFLIGHT);
    ps5log_line(PS5LOG_MARK,"ML_PHASE phase=Initializing");
    VkInstance instance;
    VkInstanceCreateInfo ici={.sType=VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO};
    CHECK(vkCreateInstance(&ici,NULL,&instance));
    uint32_t count=1; VkPhysicalDevice physical;
    CHECK(vkEnumeratePhysicalDevices(instance,&count,&physical));
    if(count!=1) fail("physical-device-count",(int)count);
    VkPhysicalDeviceProperties properties; vkGetPhysicalDeviceProperties(physical,&properties);
    ps5log_printf(PS5LOG_MARK,"ML_DEVICE name=%s api=%u",properties.deviceName,properties.apiVersion);
    float priority=1;
    VkDeviceQueueCreateInfo qci={.sType=VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO,.queueCount=1,.pQueuePriorities=&priority};
    VkDeviceCreateInfo dci={.sType=VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO,.queueCreateInfoCount=1,.pQueueCreateInfos=&qci};
    VkDevice device; CHECK(vkCreateDevice(physical,&dci,NULL,&device));
    if(ML_PREFLIGHT) {
        vkDestroyDevice(device,NULL); vkDestroyInstance(instance,NULL);
        ps5log_line(PS5LOG_MARK,"ML_PREFLIGHT_PASS device-created-and-destroyed no-dispatch");
        ps5log_close("preflight-complete"); _exit(0);
    }
    VkQueue queue; vkGetDeviceQueue(device,0,0,&queue);
    VkDescriptorSetLayoutBinding bindings[3];
    for(unsigned i=0;i<3;i++) bindings[i]=(VkDescriptorSetLayoutBinding){i,VK_DESCRIPTOR_TYPE_STORAGE_BUFFER,1,VK_SHADER_STAGE_COMPUTE_BIT,NULL};
    VkDescriptorSetLayoutCreateInfo slci={.sType=VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO,.bindingCount=3,.pBindings=bindings};
    VkDescriptorSetLayout sl; CHECK(vkCreateDescriptorSetLayout(device,&slci,NULL,&sl));
    VkPipelineLayoutCreateInfo plci={.sType=VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO,.setLayoutCount=1,.pSetLayouts=&sl};
    VkPipelineLayout layout; CHECK(vkCreatePipelineLayout(device,&plci,NULL,&layout));
    VkPipeline pipelines[2];
    ps5log_line(PS5LOG_MARK,"ML_PHASE phase=Compiling");
    for(unsigned p=0;p<2;p++) {
        const uint32_t *code=p?dense_spirv:matmul_spirv;
        size_t size=p?sizeof(dense_spirv):sizeof(matmul_spirv);
        VkShaderModuleCreateInfo smci={.sType=VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO,.codeSize=size,.pCode=code};
        VkShaderModule module; CHECK(vkCreateShaderModule(device,&smci,NULL,&module));
        VkComputePipelineCreateInfo pci={.sType=VK_STRUCTURE_TYPE_COMPUTE_PIPELINE_CREATE_INFO,.layout=layout,
            .stage={.sType=VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO,.stage=VK_SHADER_STAGE_COMPUTE_BIT,.module=module,.pName="main"}};
        uint64_t start=ns();
        CHECK(vkCreateComputePipelines(device,VK_NULL_HANDLE,1,&pci,NULL,&pipelines[p]));
        ps5log_printf(PS5LOG_MARK,"ML_PIPELINE kind=%u compile_ns=%llu",p,(unsigned long long)(ns()-start));
        vkDestroyShaderModule(device,module,NULL);
    }
    VkDescriptorPoolSize size={VK_DESCRIPTOR_TYPE_STORAGE_BUFFER,3};
    VkDescriptorPoolCreateInfo dpci={.sType=VK_STRUCTURE_TYPE_DESCRIPTOR_POOL_CREATE_INFO,.maxSets=1,.poolSizeCount=1,.pPoolSizes=&size};
    VkDescriptorPool pool; CHECK(vkCreateDescriptorPool(device,&dpci,NULL,&pool));
    VkDescriptorSetAllocateInfo dsai={.sType=VK_STRUCTURE_TYPE_DESCRIPTOR_SET_ALLOCATE_INFO,.descriptorPool=pool,.descriptorSetCount=1,.pSetLayouts=&sl};
    VkDescriptorSet set; CHECK(vkAllocateDescriptorSets(device,&dsai,&set));
    VkBuffer buffers[3]; VkDeviceMemory memory[3]; uint32_t *mapped[3]; VkMappedMemoryRange ranges[3];
    VkPhysicalDeviceMemoryProperties mp; vkGetPhysicalDeviceMemoryProperties(physical,&mp);
    for(unsigned b=0;b<3;b++) {
        VkBufferCreateInfo bci={.sType=VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO,.size=WORDS*4,.usage=VK_BUFFER_USAGE_STORAGE_BUFFER_BIT};
        CHECK(vkCreateBuffer(device,&bci,NULL,&buffers[b]));
        VkMemoryRequirements req; vkGetBufferMemoryRequirements(device,buffers[b],&req);
        uint32_t type=0;
        for(;type<mp.memoryTypeCount;type++) if((req.memoryTypeBits&(1u<<type))&&(mp.memoryTypes[type].propertyFlags&VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT)) break;
        if(type==mp.memoryTypeCount) fail("host-visible-memory",-1);
        VkMemoryAllocateInfo mai={.sType=VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO,.allocationSize=req.size,.memoryTypeIndex=type};
        CHECK(vkAllocateMemory(device,&mai,NULL,&memory[b]));
        CHECK(vkBindBufferMemory(device,buffers[b],memory[b],0));
        CHECK(vkMapMemory(device,memory[b],0,VK_WHOLE_SIZE,0,(void **)&mapped[b]));
        ranges[b]=(VkMappedMemoryRange){.sType=VK_STRUCTURE_TYPE_MAPPED_MEMORY_RANGE,.memory=memory[b],.size=VK_WHOLE_SIZE};
    }
    const unsigned elements[3]={M*K,K*N+N,ELEMENTS};
    for(unsigned b=0;b<3;b++) {
        VkDescriptorBufferInfo bi={buffers[b],FIRST*4,elements[b]*4};
        VkWriteDescriptorSet write={.sType=VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET,.dstSet=set,.dstBinding=b,.descriptorCount=1,.descriptorType=VK_DESCRIPTOR_TYPE_STORAGE_BUFFER,.pBufferInfo=&bi};
        vkUpdateDescriptorSets(device,1,&write,0,NULL);
    }
    VkCommandPoolCreateInfo cpci={.sType=VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO,.flags=VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT};
    VkCommandPool commands; CHECK(vkCreateCommandPool(device,&cpci,NULL,&commands));
    VkCommandBufferAllocateInfo cbai={.sType=VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO,.commandPool=commands,.level=VK_COMMAND_BUFFER_LEVEL_PRIMARY,.commandBufferCount=1};
    VkCommandBuffer cb; CHECK(vkAllocateCommandBuffers(device,&cbai,&cb));
    VkFenceCreateInfo fci={.sType=VK_STRUCTURE_TYPE_FENCE_CREATE_INFO};
    VkFence fence; CHECK(vkCreateFence(device,&fci,NULL,&fence));
    ps5log_line(PS5LOG_MARK,"ML_PHASE phase=Running");
    for(unsigned round=0;round<3;round++) for(unsigned kind=0;kind<2;kind++) {
        uint32_t poison=0x7fc10000u+round*2+kind;
        for(unsigned b=0;b<3;b++) for(unsigned i=0;i<WORDS;i++) mapped[b][i]=poison;
        float *x=(float *)(mapped[0]+FIRST), *w=(float *)(mapped[1]+FIRST), *y=(float *)(mapped[2]+FIRST);
        for(unsigned i=0;i<M*K;i++) x[i]=xvalue(i,round);
        for(unsigned i=0;i<K*N;i++) w[i]=wvalue(i,round);
        for(unsigned i=0;i<N;i++) w[K*N+i]=bias(i,round);
        CHECK(vkFlushMappedMemoryRanges(device,3,ranges));
        CHECK(vkResetFences(device,1,&fence)); CHECK(vkResetCommandBuffer(cb,0));
        VkCommandBufferBeginInfo begin={.sType=VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO};
        CHECK(vkBeginCommandBuffer(cb,&begin));
        barrier(cb,VK_PIPELINE_STAGE_HOST_BIT,VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT,VK_ACCESS_HOST_WRITE_BIT,VK_ACCESS_SHADER_READ_BIT|VK_ACCESS_SHADER_WRITE_BIT);
        vkCmdBindPipeline(cb,VK_PIPELINE_BIND_POINT_COMPUTE,pipelines[kind]);
        vkCmdBindDescriptorSets(cb,VK_PIPELINE_BIND_POINT_COMPUTE,layout,0,1,&set,0,NULL);
        vkCmdDispatch(cb,(ELEMENTS+63)/64,1,1);
        barrier(cb,VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT,VK_PIPELINE_STAGE_HOST_BIT,VK_ACCESS_SHADER_WRITE_BIT,VK_ACCESS_HOST_READ_BIT);
        CHECK(vkEndCommandBuffer(cb));
        VkSubmitInfo submit={.sType=VK_STRUCTURE_TYPE_SUBMIT_INFO,.commandBufferCount=1,.pCommandBuffers=&cb};
        uint64_t start=ns();
        CHECK(vkQueueSubmit(queue,1,&submit,fence));
        CHECK(vkWaitForFences(device,1,&fence,VK_TRUE,5000000000ull));
        CHECK(vkInvalidateMappedMemoryRanges(device,3,ranges));
        uint64_t elapsed=ns()-start;
        unsigned errors=0,guards=0,input_errors=0; float max_error=0;
        for(unsigned row=0;row<M;row++) for(unsigned col=0;col<N;col++) {
            // CPU oracle recomputes inputs independently and never writes GPU output.
            double ref=0;
            for(unsigned k=0;k<K;k++) ref+=(double)xvalue(row*K+k,round)*wvalue(k*N+col,round);
            if(kind) ref=fmax(ref+bias(col,round),0.0);
            float actual=y[row*N+col], error=fabsf(actual-(float)ref);
            if(!__builtin_isfinite(actual)||error>0.0001f) errors++;
            if(error>max_error) max_error=error;
            ps5log_printf(PS5LOG_INFO,"ML_VALUE round=%u kind=%u index=%u actual=%.8g expected=%.8g",round,kind,row*N+col,(double)actual,ref);
        }
        for(unsigned b=0;b<3;b++) for(unsigned i=0;i<WORDS;i++)
            if(i<FIRST||i>=FIRST+elements[b]) guards+=mapped[b][i]!=poison;
        for(unsigned i=0;i<M*K;i++) input_errors+=x[i]!=xvalue(i,round);
        for(unsigned i=0;i<K*N;i++) input_errors+=w[i]!=wvalue(i,round);
        for(unsigned i=0;i<N;i++) input_errors+=w[K*N+i]!=bias(i,round);
        ps5log_printf(PS5LOG_MARK,"ML_RESULT round=%u kind=%u checked=%u errors=%u guard_errors=%u input_errors=%u max_abs_error=%.8g submit_wait_readback_ns=%llu",round,kind,ELEMENTS,errors,guards,input_errors,(double)max_error,(unsigned long long)elapsed);
        if(errors||guards||input_errors) fail("readback-oracle",-1);
    }
    ps5log_line(PS5LOG_MARK,"ML_PHASE phase=Cleanup");
    CHECK(vkDeviceWaitIdle(device));
    vkDestroyFence(device,fence,NULL); vkDestroyCommandPool(device,commands,NULL);
    vkDestroyDescriptorPool(device,pool,NULL);
    for(unsigned b=0;b<3;b++) {vkUnmapMemory(device,memory[b]);vkDestroyBuffer(device,buffers[b],NULL);vkFreeMemory(device,memory[b],NULL);}
    for(unsigned p=0;p<2;p++) vkDestroyPipeline(device,pipelines[p],NULL);
    vkDestroyPipelineLayout(device,layout,NULL); vkDestroyDescriptorSetLayout(device,sl,NULL);
    vkDestroyDevice(device,NULL); vkDestroyInstance(instance,NULL);
    ps5log_line(PS5LOG_MARK,"ML_PASS cases=6 values=546 model=dense-relu-fp32 gpu-submission=6");
#if !ML_DASHBOARD
    ps5log_close("complete");
#endif
    return 0;
}
#if !ML_DASHBOARD
int main(void) { int result=ml_run();_exit(result); }
#endif
