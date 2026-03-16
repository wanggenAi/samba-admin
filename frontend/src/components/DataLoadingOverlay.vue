<template>
  <transition name="overlay-fade">
    <div v-if="show" class="data-loading-overlay" aria-live="polite" aria-busy="true">
      <div class="data-loading-content" role="status" aria-label="Loading">
        <span class="data-loading-spinner" aria-hidden="true"></span>
        <span class="data-loading-text">{{ text }}</span>
      </div>
    </div>
  </transition>
</template>

<script setup>
const props = defineProps({
  show: { type: Boolean, default: false },
  text: { type: String, default: "Loading..." },
});
</script>

<style scoped>
.data-loading-overlay {
  position: absolute;
  inset: 0;
  background: rgba(255, 255, 255, 0.72);
  backdrop-filter: blur(0.6px);
  z-index: 8;
}

/*
  Keep the loading indicator centered in the viewport so it stays visually centered
  even when the parent area is horizontally scrolled or browser zoom percentage changes.
*/
.data-loading-content {
  position: fixed;
  left: 50%;
  top: 50%;
  transform: translate(-50%, -50%);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 10px 14px;
  border: 1px solid #dbe3ef;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.96);
  box-shadow: 0 10px 30px rgba(15, 23, 42, 0.14);
  max-width: calc(100vw - 32px);
}

.data-loading-spinner {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  border: 2px solid #d6e3f5;
  border-top-color: #2563eb;
  animation: data-loading-spin 0.8s linear infinite;
}

.data-loading-text {
  color: #334155;
  font-size: 13px;
  font-weight: 600;
  white-space: nowrap;
}

.overlay-fade-enter-active,
.overlay-fade-leave-active {
  transition: opacity 0.04s linear;
}

.overlay-fade-enter-from,
.overlay-fade-leave-to {
  opacity: 0;
}

@keyframes data-loading-spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
