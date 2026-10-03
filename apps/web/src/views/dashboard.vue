<template>
  <div class="dashboard-container">
    <!-- 危机工单待处理数：看板第一屏应回答「今天有没有人需要我」，
         不能只把这个数字藏在侧边栏角标里 -->
    <el-alert
      v-if="pendingCrisis > 0"
      type="error"
      :closable="false"
      class="crisis-banner"
    >
      <template #title>
        <div class="crisis-banner__inner">
          <span>有 <b>{{ pendingCrisis }}</b> 条危机工单待处理 —— 危机预警不等人</span>
          <el-button type="danger" size="small" @click="router.push('/back/crisis')">
            立即处理
          </el-button>
        </div>
      </template>
    </el-alert>

    <el-row :gutter="20">
      <el-col :span="6">
        <el-card v-if="aiData.systemOverview">
          <div class="card-content">
            <div class="avatar users">
              <el-image style="width: 40px; height: 40px" :src="iconUrl1" />
            </div>
            <div class="info">
              <p class="title">总用户数</p>
              <p class="number">{{ aiData.systemOverview.totalUsers }}</p>
              <p class="subtitle-title">活跃用户：{{ aiData.systemOverview.activeUsers }}</p>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card v-if="aiData.systemOverview">
          <div class="card-content">
            <div class="avatar like">
              <el-image style="width: 40px; height: 40px" :src="iconUrl2" />
            </div>
            <div class="info">
              <p class="title">情绪日志</p>
              <p class="number">{{ aiData.systemOverview.totalDiaries }}</p>
              <p class="subtitle-title">今日新增：{{ aiData.systemOverview.todayNewDiaries }}</p>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card v-if="aiData.systemOverview">
          <div class="card-content">
            <div class="avatar comments">
              <el-image style="width: 40px; height: 40px" :src="iconUrl3" />
            </div>
            <div class="info">
              <p class="title">咨询会话</p>
              <p class="number">{{ aiData.systemOverview.totalSessions }}</p>
              <p class="subtitle-title">今日新增：{{ aiData.systemOverview.todayNewSessions }}</p>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card v-if="aiData.systemOverview">
          <div class="card-content">
            <div class="avatar smile">
              <el-image style="width: 40px; height: 40px" :src="iconUrl4" />
            </div>
            <div class="info">
              <p class="title">平均情绪</p>
              <p class="number">{{ aiData.systemOverview.avgMoodScore }}/10</p>
              <p class="subtitle-title">情绪健康指数</p>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>
    <el-row style="margin-top: 20px;" :gutter="20">
      <el-col :span="12">
        <el-card style="width: 100%">
          <template #header>
            <div class="card-header">
              <span>情绪趋势分析</span>
              <!-- 数据很稀疏时，单看一条折线容易过度解读，所以把覆盖天数写在标题旁 -->
              <span class="card-header__hint">
                近 7 天中有 {{ daysWithData }} 天有记录
              </span>
            </div>
          </template>
          <div class="chart-content">
            <div ref="emotionChartRef" style="width: 100%; height:300px"></div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card style="width: 100%">
          <template #header>
            <div class="card-header">
              咨询会话统计
            </div>
          </template>
          <div class="chart-content">
            <div v-if="aiData.consultationStats" class="consultation-stats">
              <div class="stat-item">
                <div class="stat-label">总会话数</div>
                <div class="stat-value">{{ aiData.consultationStats.totalSessions }}</div>
              </div>
              <div class="stat-item">
                <div class="stat-label">人均消息数</div>
                <div class="stat-value">{{ aiData.consultationStats.avgMessagesPerSession }}</div>
              </div>
              <div class="stat-item">
                <div class="stat-label">活跃用户</div>
                <div class="stat-value">{{ aiData.systemOverview.activeUsers }}</div>
              </div>
            </div>
            <div ref="consultationChartRef" style="width: 100%; height:260px"></div>
          </div>
        </el-card>
      </el-col>
    </el-row>
    <el-row style="margin-top: 20px;">
      <el-card style="width: 100%">
        <template #header>
          <div class="card-header">
            用户活跃度趋势
          </div>
        </template>
        <div class="chart-content">
          <div ref="userActivityChartRef" style="width: 100%; height:300px"></div>
        </div>
      </el-card>
    </el-row>
  </div>
</template>
<script setup>
import { getAnalyticsOverview, getCrisisPendingCount } from '@/api/admin'
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import * as echarts from 'echarts'
import { countDaysWithData, toCountSeries, toMoodSeries } from '@/utils/analyticsChart'

const router = useRouter()

// 统计图片引入
const iconUrl1 = new URL('@/assets/images/users.png', import.meta.url).href
const iconUrl2 = new URL('@/assets/images/like.png', import.meta.url).href
const iconUrl3 = new URL('@/assets/images/comments.png', import.meta.url).href
const iconUrl4 = new URL('@/assets/images/smile.png', import.meta.url).href

const aiData = ref({})
// 危机工单待处理数（>0 时看板顶部出现红色横幅）
const pendingCrisis = ref(0)

/**
 * 近 7 天里真正有记录的天数。
 *
 * 为什么要在看板上显示这个：数据往往很稀疏（几天才有一条），
 * 只看一条折线容易把「没人记录」误读成「情绪变化」。
 */
const daysWithData = computed(() => countDaysWithData(aiData.value?.trendData || []))

// 初始化图表
const initCharts = () => {
  // 逐个 try/catch：任何一个图表因数据缺失而失败，都不该拖垮另外两个。
  // （之前是三个连着调，第一个抛错后两个就再也不会执行了。）
  const charts = [initEmotionChart, initConsultationChart, initUserActivityChart]
  charts.forEach((fn) => {
    try {
      fn()
    } catch (err) {
      console.error('[dashboard] 图表初始化失败：', fn.name, err)
    }
  })
}

// 情绪趋势
let emotionChart = null
const emotionChartRef = ref(null)
const initEmotionChart = () => {
  if (!emotionChartRef.value) return
  // 销毁现有的图表
  if (emotionChart) {
    emotionChart.dispose()
  }
  // 创建echarts实例
  emotionChart = echarts.init(emotionChartRef.value)
  // 获取情绪趋势的数据
  const TrendData = aiData.value.trendData
  // 配置项
  const option = {
    // 这里**不再放 echarts 自己的 title** —— 卡片头部已经有一个「情绪趋势分析」，
    // 两边都写会重复显示，而且 echarts 的两行标题（text + subtext）还会和图例打架。
    // 标题与「N 天有记录」的提示都放到卡片头部（见模板）。
    tooltip: {
      trigger: 'axis',
      borderColor: '#abded7',
      borderWidth: 1,
      textStyle: {
        color: '#3c5750'
      },
      // 无记录的天要说清「无记录」，不能显示成「情绪评分 0」
      formatter: (params) => {
        const day = TrendData.find((d) => d.date === params[0].axisValue)
        if (day && day.recordCount === 0) {
          return `${params[0].axisValue}<br/>当天没有记录`
        }
        return params
          .filter((p) => p.value !== null && p.value !== undefined)
          .map((p) => `${p.marker}${p.seriesName}：${p.value}`)
          .join('<br/>')
      }
    },
    legend: {
      data: ['平均情绪评分', '记录数量'],
      // 图表内已无标题，图例可以贴顶
      top: 8
    },
    grid: { // 控制容器样式
      left: '3%',
      right: '4%',
      top: 48,
      bottom: '3%'
    },
    xAxis: {
      type: 'category',
      data: TrendData.map(item => item.date),
      axisLine: {
        lineStyle: {
          color: '#3c5750'
        }
      }
    },
    yAxis: [{
      type: 'value',
      name: '情绪评分',
      position: 'left',
      axisLine: {
        lineStyle: {
          color: '#3c5750'
        }
      }
    }, {
      type: 'value',
      name: '记录数量',
      position: 'right',
      axisLine: {
        lineStyle: {
          color: '#3c5750'
        }
      }
    }],
    series: [{
      name: '平均情绪评分',
      type: 'line',
      // 无记录的天置 null（不是 0），让折线断开 —— 详见 utils/analyticsChart.js
      data: toMoodSeries(TrendData),
      connectNulls: false,
      smooth: true,
      lineStyle: {
        width: 3,
        color: '#7cc9bf'
      },
      itemStyle: {
        color: '#7cc9bf'
      }
    },
    {
      name: '记录数量',
      type: 'line',
      data: toCountSeries(TrendData),
      smooth: true,
      lineStyle: {
        width: 3,
        color: '#52b2a4'
      },
      itemStyle: {
        color: '#52b2a4'
      }
    }]
  }

  emotionChart.setOption(option)
}

// 咨询会话统计
let consultationChart = null
const consultationChartRef = ref(null)
const initConsultationChart = () => {
  if (!consultationChartRef.value) return
  // 销毁现有的图表
  if (consultationChart) {
    consultationChart.dispose()
  }
  // 创建echarts实例
  consultationChart = echarts.init(consultationChartRef.value)
  // 获取数据
  const dailyTrend = aiData.value.dailyTrend
  const option = {
    title: {
      text: '咨询活动统计',
      textStyle: {
        fontSize: 16,
        fontWeight: 600,
        color: '#3c5750'
      },
      left: 'center',
      top: 10
    },
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(255, 255, 255, 0.95)',
      borderColor: '#abded7',
      borderWidth: 1,
      textStyle: {
        color: '#3c5750'
      }
    },
    legend: {
      data: ['会话数量', '参与用户数'],
      top: 40,
      textStyle: {
        color: '#6d837c'
      }
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '3%',
      top: 80,
      containLabel: true
    },
    xAxis: {
      type: 'category',
      data: dailyTrend.map(item => item.date),
      axisLine: {
        lineStyle: {
          color: 'rgba(239, 171, 60, 0.3)'
        }
      },
      axisLabel: {
        color: '#6d837c'
      }
    },
    yAxis: {
      type: 'value',
      axisLabel: {
        color: '#6d837c'
      },
      axisLine: {
        lineStyle: {
          color: 'rgba(239, 171, 60, 0.3)'
        }
      },
      splitLine: {
        lineStyle: {
          color: 'rgba(244, 162, 97, 0.1)'
        }
      }
    },
    series: [
      {
        name: '会话数量',
        type: 'bar',
        data: dailyTrend.map(item => item.sessionCount),
        itemStyle: {
          color: {
            type: 'linear',
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: '#74b9ff' },
              { offset: 1, color: '#0984e3' }
            ]
          }
        },
        barWidth: '40%'
      },
      {
        name: '参与用户数',
        type: 'bar',
        data: dailyTrend.map(item => item.userCount),
        itemStyle: {
          color: {
            type: 'linear',
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: '#efab3c' },
              { offset: 1, color: '#d98f22' }
            ]
          }
        },
        barWidth: '40%'
      }
    ]
  }
  consultationChart.setOption(option)
}

// 用户活跃度分析
let userActivityChart = null
const userActivityChartRef = ref(null)
const initUserActivityChart = () => {
  if (!userActivityChartRef.value) return
  // 销毁现有的图表
  if (userActivityChart) {
    userActivityChart.dispose()
  }
  // 创建echarts实例
  userActivityChart = echarts.init(userActivityChartRef.value)
  // 获取数据
  const activityData = aiData.value.activityData
  const option = {
    title: {
      text: '用户活跃度趋势',
      textStyle: {
        fontSize: 16,
        fontWeight: 600,
        color: '#3c5750'
      },
      left: 'center',
      top: 10
    },
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(255, 255, 255, 0.95)',
      borderColor: '#abded7',
      borderWidth: 1,
      textStyle: {
        color: '#3c5750'
      }
    },
    legend: {
      data: ['活跃用户', '新增用户', '日记用户', '咨询用户'],
      top: 40,
      textStyle: {
        color: '#6d837c'
      }
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '3%',
      top: 80,
      containLabel: true
    },
    xAxis: {
      type: 'category',
      data: activityData.map(item => item.date),
      axisLine: {
        lineStyle: {
          color: 'rgba(239, 171, 60, 0.3)'
        }
      },
      axisLabel: {
        color: '#6d837c'
      }
    },
    yAxis: {
      type: 'value',
      axisLabel: {
        color: '#6d837c'
      },
      axisLine: {
        lineStyle: {
          color: 'rgba(239, 171, 60, 0.3)'
        }
      },
      splitLine: {
        lineStyle: {
          color: 'rgba(244, 162, 97, 0.1)'
        }
      }
    },
    series: [
      {
        name: '活跃用户',
        type: 'line',
        data: activityData.map(item => item.activeUsers),
        smooth: true,
        lineStyle: {
          width: 3,
          color: '#5786e0'
        },
        itemStyle: {
          color: '#5786e0'
        },
        areaStyle: {
          color: {
            type: 'linear',
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: 'rgba(162, 155, 254, 0.4)' },
              { offset: 1, color: 'rgba(162, 155, 254, 0.1)' }
            ]
          }
        }
      },
      {
        name: '新增用户',
        type: 'line',
        data: activityData.map(item => item.newUsers),
        smooth: true,
        lineStyle: {
          width: 3,
          color: '#efab3c'
        },
        itemStyle: {
          color: '#efab3c'
        }
      },
      {
        name: '日记用户',
        type: 'line',
        data: activityData.map(item => item.diaryUsers),
        smooth: true,
        lineStyle: {
          width: 3,
          color: '#2c9e6a'
        },
        itemStyle: {
          color: '#2c9e6a'
        }
      },
      {
        name: '咨询用户',
        type: 'line',
        data: activityData.map(item => item.consultationUsers),
        smooth: true,
        lineStyle: {
          width: 3,
          color: '#abded7'
        },
        itemStyle: {
          color: '#abded7'
        }
      }
    ]
  }
  userActivityChart.setOption(option)
}

let isUnmounted = false

onMounted(() => {
  // 危机待处理数：拉不到不阻塞看板（角标仍在侧边栏兜底）
  getCrisisPendingCount()
    .then((n) => {
      pendingCrisis.value = Number(n) || 0
    })
    .catch(() => {})

  getAnalyticsOverview().then(async (res) => {
    // 请求返回前若组件已卸载，则不再初始化图表，避免泄漏
    if (isUnmounted) return
    aiData.value = res

    // 必须等 DOM 更新后再初始化图表：
    // 这三个图表容器都在 `v-if="aiData.xxx"` 内部，赋值后同步调用 initCharts()
    // 时容器还没渲染出来，ref 全是 null —— 图表会静默地一个都不创建
    // （构建和单元测试都发现不了，只有真实浏览器能暴露）。
    await nextTick()
    if (isUnmounted) return
    initCharts()
  })
})

// 卸载时释放 ECharts 实例，避免内存泄漏与画布残留（P0-7 / F9）
onUnmounted(() => {
  isUnmounted = true
  emotionChart?.dispose()
  emotionChart = null
  consultationChart?.dispose()
  consultationChart = null
  userActivityChart?.dispose()
  userActivityChart = null
})
</script>
<style lang="scss" scoped>
/* 危机待处理横幅：看板第一屏最先被看到的位置 */
.crisis-banner {
  margin-bottom: 16px;

  .crisis-banner__inner {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    width: 100%;

    b {
      font-size: 16px;
    }
  }
}

/* 卡片头部：标题 + 右侧弱化提示 */
.card-header {
  display: flex;
  align-items: baseline;
  gap: 10px;
  flex-wrap: wrap;

  &__hint {
    font-size: 12.5px;
    font-weight: 400;
    color: var(--nd-text-3);
  }
}

.dashboard-container {
  .card-content {
    display: flex;
    align-items: center;

    .avatar {
      margin-right: 12px;
      width: 60px;
      height: 60px;
      border-radius: 12px;
      display: flex;
      align-items: center;
      justify-content: center;

      &.users {
        background: linear-gradient(135deg, #52b2a4 0%, #23857a 100%);
      }

      &.like {
        background: linear-gradient(135deg, #7cc9bf 0%, #2f9c8b 100%);
      }

      &.comments {
        background: linear-gradient(135deg, #efab3c 0%, #d98f22 100%);
      }

      &.smile {
        background: linear-gradient(135deg, #5786e0 0%, #3f68bd 100%);
      }
    }

    .info {
      .title {
        font-size: 14px;
        color: var(--nd-text-3);
        margin-bottom: 4px;
      }

      .value {
        font-size: 24px;
        font-weight: 700;
        color: var(--nd-text-1);
        margin-bottom: 4px
      }

      .subtitle-title {
        font-size: 12px;
        color: var(--nd-text-4);
      }
    }
  }

  .chart-content {
    padding: 20px;
    height: 300px;
    position: relative;

    canvas {
      width: 100% !important;
      height: 100% !important;
    }

    .consultation-stats {
      display: flex;
      justify-content: space-around;
      margin-bottom: 20px;

      .stat-item {
        text-align: center;

        .stat-label {
          font-size: 12px;
          color: var(--nd-text-3);
          margin-bottom: 4px;
        }

        .stat-value {
          font-size: 18px;
          font-weight: 600;
          color: var(--nd-text-1);
        }
      }
    }
  }
}
</style>
