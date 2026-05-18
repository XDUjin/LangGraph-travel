<template>
  <div id="app">
    <a-layout style="min-height: 100vh">
      <a-layout-header style="background: #001529; padding: 0 50px; display: flex; align-items: center; justify-content: space-between">
        <div
          style="color: white; font-size: 24px; font-weight: bold; cursor: pointer"
          @click="$router.push('/')"
        >
          🌍 多agent的智能旅行助手
        </div>
        <a-space size="large">
          <a-button type="link" style="color: white" @click="$router.push('/')">
            🗺️ 旅行规划
          </a-button>
          <a-button type="link" style="color: white" @click="$router.push('/chat')">
            📚 知识问答
          </a-button>
        </a-space>
      </a-layout-header>
      <a-layout-content style="padding: 24px">
        <router-view />
      </a-layout-content>
      <a-layout-footer style="text-align: center">
        多agent的智能旅行助手 ©2025
      </a-layout-footer>
    </a-layout>
  </div>
</template>

<script setup lang="ts">
</script>

<style>
#app {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial,
    'Noto Sans', sans-serif;
}
</style>

