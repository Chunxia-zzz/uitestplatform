<script setup lang="ts">
</script>

<template>
  <div class="app-shell">
    <header class="topbar">
      <div class="brand">UI 自动化平台 <small>多引擎 · 元素库 · Playwright</small></div>
      <nav class="nav">
        <router-link to="/scaffold">快速接入</router-link>
        <router-link to="/scan">元素扫描</router-link>
        <router-link to="/elements">元素库</router-link>
        <router-link to="/cases">用例编排</router-link>
        <router-link to="/suites">用例集</router-link>
        <router-link to="/engines">引擎与能力</router-link>
        <router-link to="/executions">执行结果</router-link>
      </nav>
      <div class="grow"></div>
      <a class="muted" href="/healthz" target="_blank" rel="noreferrer">健康检查</a>
    </header>
    <main class="page">
      <router-view />
    </main>
  </div>
</template>
