<template>
    <el-dialog
        :title="isEdit ? '编辑文章' : '新增文章'"
        v-model="dialogVisible"
        width="50%"
        @close="handleClose"
    >
        <el-form :model="formData" :rules="rules" ref="formRef" label-width="120px">
            <el-form-item label="文章标题" prop="title">
                <el-input v-model="formData.title" placeholder="请输入文章标题" maxlength="200" show-word-limit clearable />
            </el-form-item>
            <el-form-item label="所属分类" prop="categoryId">
                <el-select v-model="formData.categoryId" placeholder="请选择分类">
                    <el-option v-for="item in props.categories" :key="item.value" :label="item.label" :value="item.value" />
                </el-select>
            </el-form-item>
            <el-form-item label="文章摘要" prop="summary">
                <el-input type="textarea" v-model="formData.summary" placeholder="请输入文章摘要(可选)" maxlength="1000" show-word-limit :rows="4" />
            </el-form-item>
            <el-form-item label="标签" prop="tags">
                <el-select v-model="formData.tagArray" placeholder="请输入文章标签(逗号分隔)" multiple filterable allow-create style="width: 100%">
                    <el-option v-for="tag in commonTags" :key="tag" :label="tag" :value="tag" />
                </el-select>
            </el-form-item>
            <el-form-item label="封面图片">
                <div class="cover-upload">
                    <el-upload
                        class="avatar-uploader"
                        action="#"
                        :before-upload="beforeUpload"
                        :http-request="handleUploadRequest"
                        :show-file-list="false"
                        accept="image/*"
                    >
                        <div v-if="!imgUrl" class="cover-placeholder">
                            <p>点击上传封面</p>
                        </div>
                        <img v-else :src="imgUrl" class="cover-image" alt="封面图片" />
                    </el-upload>
                    <div v-if="imgUrl" class="cover-remove">
                        <el-button type="danger" size="mini" @click="handleRemove">移除封面</el-button>
                    </div>
                </div>
            </el-form-item>
            <el-form-item label="文章内容" prop="content">
                <!-- 文档导入：解析后预填到编辑器，人工校对后再保存（不直接入库，见后端 doc_import.py） -->
                <div class="import-bar">
                    <el-upload
                        :show-file-list="false"
                        :http-request="handleDocImport"
                        accept=".txt,.md,.docx,.pdf"
                    >
                        <el-button size="small" :loading="importing">
                            <el-icon><Upload /></el-icon>
                            从文档导入（txt / md / docx / pdf）
                        </el-button>
                    </el-upload>
                    <span class="import-hint">导入会覆盖当前内容，请在校对后再保存</span>
                </div>
                <RichTextEditor
                    v-model="formData.content"
                    placeholder="请输入文章内容，支持富文本格式\n\n可以使用加粗、斜体、列表、标题等格式来丰富文章内容。"
                    :maxCharCount="5000"
                    @change="handleContentChange"
                    @created="handleEditorCreated"
                    min-height="400px"
                    />
            </el-form-item>
        </el-form>
        <div v-if="btnPreview">
            <h3>内容预览</h3>
            <div v-html="sanitizeHtml(formData.content)"></div>
        </div>
        <template #footer>
            <el-button @click="btnPreview = !btnPreview">{{ btnPreview ? '隐藏预览' : '预览效果' }}</el-button>
            <el-button @click="handleClose">取消</el-button>
            <el-button type="primary" @click="handleSubmit" :loading="loading">{{ isEdit ? '更新文章' : '创建文章' }}</el-button>
        </template>
    </el-dialog>
</template>
<script setup>
import { sanitizeHtml } from '@/utils/sanitize'
import { ref, reactive, computed, nextTick, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { uploadFile, createArticle, updateArticle, importDocument } from '@/api/admin'
import { fileBaseUrl } from '@/config/index.js'
import RichTextEditor from '@/components/RichTextEditor.vue'

const props = defineProps({
    modelValue: {
        type: Boolean,
        default: false
    },
    categories: {
        type: Array,
        default: () => []
    },
    article: {
        type: Object,
        default: null
    }
})

const emit = defineEmits(['update:modelValue', 'success'])

const dialogVisible = computed({
    get() {
        return props.modelValue
    },
    set(val) {
        emit('update:modelValue', val)
    }
})

const isEdit = computed(() => !!props.article?.id)

// 监听编辑数据
watch(() => props.article, (newVal) => {
    if (newVal) {
        nextTick(() => {
            Object.assign(formData, newVal)
            // 使用现有ID
            businessId.value = newVal.id
            // 封面Url
            imgUrl.value = fileBaseUrl + newVal.coverImage
        })
    }
})

const handleClose = () => {
    // 重置表单
    formRef.value.resetFields()
    // 重置ID
    businessId.value = null
    // 重置标签
    formData.tagArray = []
    // 重置封面图片和数据
    handleRemove()
    emit('update:modelValue', false)
}

// 表单数据
const formData = reactive({
    "title": "",
    "content": "",
    "coverImage": "",
    "categoryId": "",
    "summary": "",
    "tags": "",
    "id": ""
})

const rules = reactive({
    title: [
        { required: true, message: '请输入文章标题', trigger: 'blur' },
        { max: 200, message: '文章标题最多200个字符', trigger: 'blur' }
    ],
    categoryId: [
        { required: true, message: '请选择分类', trigger: 'change' }
    ],
    content: [
        { required: true, message: '请输入文章内容', trigger: 'blur' },
        { max: 5000, message: '文章内容最多5000个字符', trigger: 'blur' }
    ],
})

const commonTags = [
  '情绪管理', '焦虑', '抑郁', '压力', '睡眠', 
  '冥想', '正念', '放松', '心理健康', '自我成长',
  '人际关系', '工作压力', '学习方法', '生活技巧'
]

// 上传
const imgUrl = ref('')
const beforeUpload = (file) => {
    // 针对上传的文件进行校验
    const isImage = file.type.startsWith('image/')
    const isLt5M = file.size / 1014 / 1014 < 5
    if (!isImage) {
        ElMessage.error('上传封面图片，请选择图片文件')
        return false
    }
    if (!isLt5M) {
        ElMessage.error('上传封面图片，图片大小不能超过5MB')
        return false
    }
    return true
}
const businessId = ref(null)
const handleUploadRequest = async ({ file }) => {
    // UUID生成
    businessId.value = crypto.randomUUID()
    const fileRes = await uploadFile(file, {
        businessId: businessId.value
    })

    // 拼接完整的图片地址
    imgUrl.value = fileBaseUrl + fileRes.filePath
    formData.coverImage = fileRes.filePath
}

const handleRemove = () => {
    imgUrl.value = ''
    formData.coverImage = ''
}

// 富文本
const handleContentChange = (data) => {
    formData.content = data.html
}

const editorInstance = ref(null)
const handleEditorCreated = (editor) => {
    editorInstance.value = editor
    // 编辑
    if (formData.content && editor) {
        nextTick(() => {
            editor.setHtml(formData.content)
        })
    }
}

// 文档导入（校验在请求层统一提示；这里的失败提示由后端 msg 给出，如扫描件 PDF）
const importing = ref(false)
const handleDocImport = async ({ file }) => {
    importing.value = true
    try {
        const data = await importDocument(file)
        // 标题为空才用文件名兜底，不覆盖管理员已填的标题
        if (!formData.title && data.title) formData.title = data.title
        formData.content = data.content
        // ⚠️ wangEditor 不监听外部 v-model 变化 —— 必须显式 setHtml，
        //    否则只有 formData 变了，编辑器里还是旧的（保存下去的是新内容，人却看不到）
        editorInstance.value?.setHtml(data.content)

        const tips = [...(data.warnings || [])]
        if (data.charCount > 5000) {
            tips.push(`内容约 ${data.charCount} 字，超过 5000 字上限，请拆分或精简后再保存`)
        }
        if (tips.length) {
            ElMessage.warning(tips.join('；'))
        } else {
            ElMessage.success(`已导入 ${data.charCount} 字，请校对后保存`)
        }
    } catch (e) {
        // 失败提示已由请求层统一给出（含后端对扫描件/加密文档的解释）
    } finally {
        importing.value = false
    }
}

const btnPreview = ref(false)

// 提交
const formRef = ref()
const loading = ref(false)
const handleSubmit = () => {
    formRef.value.validate((valid, fields) => {
        if (valid) {
            loading.value = true
        }
        const submitData = {
            ...formData,
            tags: formData.tagArray.join(',')
        }
        delete submitData.tagArray
        
        if (!isEdit.value) {
            submitData.id = businessId.value
            createArticle(submitData).then(res => {
                loading.value = false
                emit('success')
            })
        } else {
            updateArticle(props.article.id, submitData).then(res => {
                loading.value = false
                emit('success')
            })
        }

        

    })
}
</script>
<style lang="scss" scoped>
/* 文档导入条：按钮 + 一行提示，别让"覆盖当前内容"这件事看起来像没代价 */
.import-bar {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 8px;

    .import-hint {
        font-size: 12px;
        color: var(--nd-text-4);
    }
}

.cover-placeholder {
    width: 200px;
    height: 120px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    color: var(--nd-text-3);
    background: var(--nd-surface-soft);
}
.cover-image {
    width: 200px;
    height: 120px;
    display: block;
}
</style>
