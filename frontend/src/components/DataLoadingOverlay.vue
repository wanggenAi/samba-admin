<template>
  <transition name="overlay-fade">
    <div v-if="show" class="data-loading-overlay" aria-live="polite" aria-busy="true">
      <span class="data-loading-spinner" aria-hidden="true"></span>
      <span class="data-loading-text">{{ text }}</span>
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
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  background: rgba(255, 255, 255, 0.72);
  backdrop-filter: blur(0.6px);
  z-index: 8;
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
