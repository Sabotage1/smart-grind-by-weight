#ifdef ATOM_GPIO1_MOTOR_TEST
#include <lvgl.h>
#include <esp_heap_caps.h>
#include <cstring>

// UI objects are accessed with the flash cache enabled. Keep these allocations
// in the board's 8 MB PSRAM instead of exhausting internal Bluetooth/task RAM.
// Display DMA buffers retain their existing allocator and capability selection.
extern "C" {
void lv_mem_init(void) {}
void lv_mem_deinit(void) {}
lv_mem_pool_t lv_mem_add_pool(void*, size_t) { return nullptr; }
void lv_mem_remove_pool(lv_mem_pool_t) {}
void* lv_malloc_core(size_t size) {
    return heap_caps_malloc(size, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
}
void* lv_realloc_core(void* p, size_t size) {
    return heap_caps_realloc(p, size, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
}
void lv_free_core(void* p) { heap_caps_free(p); }
void lv_mem_monitor_core(lv_mem_monitor_t* mon) {
    multi_heap_info_t info = {};
    heap_caps_get_info(&info, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    std::memset(mon, 0, sizeof(*mon));
    mon->total_size = info.total_free_bytes + info.total_allocated_bytes;
    mon->free_size = info.total_free_bytes;
    mon->free_biggest_size = info.largest_free_block;
    mon->free_cnt = info.free_blocks;
    mon->used_cnt = info.allocated_blocks;
    mon->used_pct = mon->total_size ? 100 * info.total_allocated_bytes / mon->total_size : 0;
    mon->frag_pct = mon->free_size ? 100 - 100 * mon->free_biggest_size / mon->free_size : 0;
}
lv_result_t lv_mem_test_core(void) {
    return heap_caps_check_integrity(MALLOC_CAP_SPIRAM, false) ? LV_RESULT_OK : LV_RESULT_INVALID;
}
}
#endif
