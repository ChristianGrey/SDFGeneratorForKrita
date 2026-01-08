#include <math.h>
#include <stdint.h>
#include <stdlib.h>

#ifdef _WIN32
#define DLLEXPORT __declspec(dllexport)
#else
#define DLLEXPORT
#endif

#define INF 1e6f

// Inline core logic for maximum speed
static inline void compare(int i, int ni, float ox, float oy, float* dx, float* dy, uint32_t* seeds, float* add_dist) {
    float nx = dx[ni] + ox;
    float ny = dy[ni] + oy;
    
    // Total distance = geometric distance to seed + seed's subpixel offset
    float new_d = sqrtf(nx*nx + ny*ny) + add_dist[seeds[ni]];
    float cur_d = sqrtf(dx[i]*dx[i] + dy[i]*dy[i]) + add_dist[seeds[i]];
    
    if (new_d < cur_d) {
        dx[i] = nx;
        dy[i] = ny;
        seeds[i] = seeds[ni];
    }
}

DLLEXPORT void compute_sdf(int w, int h, uint8_t* pixels, float* out_dist, float* out_dist_in) {
    int total = w * h;
    
    float* dx = (float*)malloc(total * sizeof(float));
    float* dy = (float*)malloc(total * sizeof(float));
    float* dx_in = (float*)malloc(total * sizeof(float));
    float* dy_in = (float*)malloc(total * sizeof(float));
    uint32_t* seeds = (uint32_t*)malloc(total * sizeof(uint32_t));
    uint32_t* seeds_in = (uint32_t*)malloc(total * sizeof(uint32_t));
    float* add_dist = (float*)malloc(total * sizeof(float));
    float* add_dist_in = (float*)malloc(total * sizeof(float));

    // 1. INITIALIZE GRIDS
    for (int i = 0; i < total; i++) {
        uint8_t b = pixels[i * 4]; // Krita BGRA
        seeds[i] = seeds_in[i] = i;
        dx[i] = dy[i] = dx_in[i] = dy_in[i] = INF;
        
        add_dist[i] = (b > 1) ? (1.0f - (b / 255.0f)) : 0.0f;
        add_dist_in[i] = (b < 254) ? (b / 255.0f) : 0.0f;

        if (b > 1) { dx[i] = dy[i] = 0.0f; }
        if (b < 254) { dx_in[i] = dy_in[i] = 0.0f; }
    }

    // 2. FOUR PASS PROPAGATION (3 neighbors per pass)
    
    // Pass 1: Top-Left to Bottom-Right (L, T, TL)
    for (int y = 0; y < h; y++) {
        int y_off = y * w;
        for (int x = 0; x < w; x++) {
            int i = y_off + x;
            if (x > 0) { // Left
                compare(i, i-1, 1.0f, 0.0f, dx, dy, seeds, add_dist);
                compare(i, i-1, 1.0f, 0.0f, dx_in, dy_in, seeds_in, add_dist_in);
            }
            if (y > 0) { // Top
                compare(i, i-w, 0.0f, 1.0f, dx, dy, seeds, add_dist);
                compare(i, i-w, 0.0f, 1.0f, dx_in, dy_in, seeds_in, add_dist_in);
                if (x > 0) { // Top-Left
                    compare(i, i-w-1, 1.0f, 1.0f, dx, dy, seeds, add_dist);
                    compare(i, i-w-1, 1.0f, 1.0f, dx_in, dy_in, seeds_in, add_dist_in);
                }
            }
        }
    }

    // Pass 2: Bottom-Right to Top-Left (R, B, BR)
    for (int y = h-1; y >= 0; y--) {
        int y_off = y * w;
        for (int x = w-1; x >= 0; x--) {
            int i = y_off + x;
            if (x < w-1) { // Right
                compare(i, i+1, -1.0f, 0.0f, dx, dy, seeds, add_dist);
                compare(i, i+1, -1.0f, 0.0f, dx_in, dy_in, seeds_in, add_dist_in);
            }
            if (y < h-1) { // Bottom
                compare(i, i+w, 0.0f, -1.0f, dx, dy, seeds, add_dist);
                compare(i, i+w, 0.0f, -1.0f, dx_in, dy_in, seeds_in, add_dist_in);
                if (x < w-1) { // Bottom-Right
                    compare(i, i+w+1, -1.0f, -1.0f, dx, dy, seeds, add_dist);
                    compare(i, i+w+1, -1.0f, -1.0f, dx_in, dy_in, seeds_in, add_dist_in);
                }
            }
        }
    }

    // Pass 3: Top-Right to Bottom-Left (R, T, TR)
    for (int y = 0; y < h; y++) {
        int y_off = y * w;
        for (int x = w-1; x >= 0; x--) {
            int i = y_off + x;
            if (x < w-1) { // Right
                compare(i, i+1, -1.0f, 0.0f, dx, dy, seeds, add_dist);
                compare(i, i+1, -1.0f, 0.0f, dx_in, dy_in, seeds_in, add_dist_in);
            }
            if (y > 0) { // Top
                compare(i, i-w, 0.0f, 1.0f, dx, dy, seeds, add_dist);
                compare(i, i-w, 0.0f, 1.0f, dx_in, dy_in, seeds_in, add_dist_in);
                if (x < w-1) { // Top-Right
                    compare(i, i-w+1, -1.0f, 1.0f, dx, dy, seeds, add_dist);
                    compare(i, i-w+1, -1.0f, 1.0f, dx_in, dy_in, seeds_in, add_dist_in);
                }
            }
        }
    }

    // Pass 4: Bottom-Left to Top-Right (L, B, BL)
    for (int y = h-1; y >= 0; y--) {
        int y_off = y * w;
        for (int x = 0; x < w; x++) {
            int i = y_off + x;
            if (x > 0) { // Left
                compare(i, i-1, 1.0f, 0.0f, dx, dy, seeds, add_dist);
                compare(i, i-1, 1.0f, 0.0f, dx_in, dy_in, seeds_in, add_dist_in);
            }
            if (y < h-1) { // Bottom
                compare(i, i+w, 0.0f, -1.0f, dx, dy, seeds, add_dist);
                compare(i, i+w, 0.0f, -1.0f, dx_in, dy_in, seeds_in, add_dist_in);
                if (x > 0) { // Bottom-Left
                    compare(i, i+w-1, 1.0f, -1.0f, dx, dy, seeds, add_dist);
                    compare(i, i+w-1, 1.0f, -1.0f, dx_in, dy_in, seeds_in, add_dist_in);
                }
            }
        }
    }

    // 3. FINAL SQRT AND OUTPUT
    for (int i = 0; i < total; i++) {
        out_dist[i] = sqrtf(dx[i]*dx[i] + dy[i]*dy[i]) + add_dist[seeds[i]];
        out_dist_in[i] = sqrtf(dx_in[i]*dx_in[i] + dy_in[i]*dy_in[i]) + add_dist_in[seeds_in[i]];
    }

    free(dx); free(dy); free(dx_in); free(dy_in);
    free(seeds); free(seeds_in); free(add_dist); free(add_dist_in);
}
