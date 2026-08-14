<script setup>
// 屏幕一：首页 · 档案抽屉（模式选择）
// 职责：整页 flex 布局 + 三个文件夹抽屉手风琴
// 数据流：mock/home.js → homeSummary（未来 GET /api/home/summary）
// 动效：
//   - 抽屉开合用 grid-template-rows 0fr→1fr 过渡（.drawer.open）
//   - 手风琴：纯点击切换，同时只展开一个，默认展开 NO.01 记忆训练
//   - 文件夹凸舌随 hover/open 上移（CSS .drawer::before）
import { ref } from 'vue'
import { homeSummary } from '../mock/home'

// openIdx：当前展开的抽屉下标；null 表示全部收起
const openIdx = ref(0)
// 每个抽屉内各可选项组的单选状态：[抽屉][组] = 选中下标
const optSel = ref(homeSummary.drawers.map(d => d.optGroups.map(g => g.on)))

// 手风琴切换：点击已展开的抽屉则收起，否则只展开被点击的那个
function toggleDrawer(i) {
  openIdx.value = openIdx.value === i ? null : i
}
// 可选项胶囊：组内单选
function pickOpt(di, gi, oi) {
  optSel.value[di][gi] = oi
}
</script>

<template>
  <section class="screen active" id="s-home">
    <div class="home-head">
      <div class="meta-row">
        <span>RECALL — 记忆助手 / LOCAL</span>
        <span id="home-date">{{ homeSummary.date }}</span>
      </div>
      <h1 class="home-title">今天，<br>进行哪一场<em>面试</em>？</h1>
      <p class="home-sub">{{ homeSummary.sub }}</p>
    </div>

    <div class="drawers">
      <div
        v-for="(d, di) in homeSummary.drawers"
        :key="d.idx"
        class="drawer"
        :class="{ open: openIdx === di }"
      >
        <div class="drawer-row" @click="toggleDrawer(di)">
          <span class="drawer-idx">{{ d.idx }}</span>
          <span class="drawer-name">{{ d.name }}</span>
          <span class="drawer-hint">{{ d.hint }}</span>
        </div>
        <div class="drawer-body"><div>
          <div class="drawer-stats">
            <div class="stat" v-for="s in d.stats" :key="s.k">
              <div class="k">{{ s.k }}</div>
              <div class="v" :style="s.seal ? 'color:var(--seal)' : ''">{{ s.v }}<small v-if="s.small">{{ s.small }}</small></div>
            </div>
          </div>
          <!-- 可选项组：记忆训练 1 组（题量），面试模拟 2 组（技术栈 + 题量） -->
          <div
            v-if="d.optGroups.length"
            class="drawer-cta"
            :style="d.optGroups.length > 1
              ? 'border-top:1px solid var(--ink-12);padding-top:20px;flex-direction:column;align-items:flex-start;gap:14px'
              : 'border-top:1px solid var(--ink-12);padding-top:20px'"
          >
            <div class="opt-group" v-for="(g, gi) in d.optGroups" :key="g.label">
              <span class="opt-label">{{ g.label }}</span>
              <button
                v-for="(o, oi) in g.options"
                :key="o"
                class="opt"
                :class="[g.seal && 'opt--seal', { on: optSel[di][gi] === oi }]"
                @click.stop="pickOpt(di, gi, oi)"
              >{{ o }}</button>
            </div>
          </div>
          <div class="drawer-cta">
            <button class="btn">{{ d.cta }}</button>
            <span class="iv-note">{{ d.note }}</span>
          </div>
        </div></div>
      </div>
    </div>

    <div class="home-foot">
      <span>RECALL · 记忆助手 — 八股面试训练</span>
      <span>FIG.01 — MODE SELECT</span>
    </div>
  </section>
</template>
