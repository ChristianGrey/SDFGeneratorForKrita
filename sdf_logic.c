#include <math.h>
#include <stdint.h>

#ifdef _WIN32
#define DLLEXPORT __declspec(dllexport)
#else
#define DLLEXPORT
#endif

// We pass pointers to your array("f") and array("I") data directly
DLLEXPORT void process_compare(int i, int neigh, float ox, float oy, 
                     float* dx, float* dy, uint32_t* seed_idx, float* add_dist) {
    
    float nx = dx[neigh] + ox;
    float ny = dy[neigh] + oy;
    
    uint32_t sn = seed_idx[neigh];
    uint32_t sc = seed_idx[i];
    
    float new_dist = sqrtf(nx*nx + ny*ny) + add_dist[sn];
    float curr_dist = sqrtf(dx[i]*dx[i] + dy[i]*dy[i]) + add_dist[sc];
    
    if (new_dist < curr_dist) {
        dx[i] = nx;
        dy[i] = ny;
        seed_idx[i] = sn;
    }
}
