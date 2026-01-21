/**
 * 虚拟滚动组件
 * 用于高效渲染大量同步历史记录
 */

class VirtualScrollList {
    constructor(container, options = {}) {
        this.container = container;
        this.itemHeight = options.itemHeight || 60; // 每项高度
        this.bufferSize = options.bufferSize || 5;   // 缓冲区大小
        this.data = [];
        this.visibleStart = 0;
        this.visibleEnd = 0;
        this.scrollTop = 0;
        
        this.init();
    }
    
    init() {
        // 创建滚动容器
        this.scrollContainer = document.createElement('div');
        this.scrollContainer.className = 'virtual-scroll-container';
        this.scrollContainer.style.cssText = `
            height: 400px;
            overflow-y: auto;
            position: relative;
        `;
        
        // 创建内容容器
        this.contentContainer = document.createElement('div');
        this.contentContainer.className = 'virtual-scroll-content';
        this.contentContainer.style.position = 'relative';
        
        // 创建可见项容器
        this.visibleContainer = document.createElement('div');
        this.visibleContainer.className = 'virtual-scroll-visible';
        this.visibleContainer.style.position = 'absolute';
        
        this.contentContainer.appendChild(this.visibleContainer);
        this.scrollContainer.appendChild(this.contentContainer);
        this.container.appendChild(this.scrollContainer);
        
        // 绑定滚动事件
        this.scrollContainer.addEventListener('scroll', this.onScroll.bind(this));
    }
    
    setData(data) {
        this.data = data;
        this.updateContent();
    }
    
    onScroll() {
        this.scrollTop = this.scrollContainer.scrollTop;
        this.updateVisibleRange();
        this.renderVisibleItems();
    }
    
    updateVisibleRange() {
        const containerHeight = this.scrollContainer.clientHeight;
        const startIndex = Math.floor(this.scrollTop / this.itemHeight);
        const endIndex = Math.min(
            startIndex + Math.ceil(containerHeight / this.itemHeight),
            this.data.length - 1
        );
        
        this.visibleStart = Math.max(0, startIndex - this.bufferSize);
        this.visibleEnd = Math.min(this.data.length - 1, endIndex + this.bufferSize);
    }
    
    updateContent() {
        // 设置总高度
        const totalHeight = this.data.length * this.itemHeight;
        this.contentContainer.style.height = `${totalHeight}px`;
        
        this.updateVisibleRange();
        this.renderVisibleItems();
    }
    
    renderVisibleItems() {
        // 清空可见容器
        this.visibleContainer.innerHTML = '';
        
        // 设置可见容器位置
        const offsetY = this.visibleStart * this.itemHeight;
        this.visibleContainer.style.transform = `translateY(${offsetY}px)`;
        
        // 渲染可见项
        for (let i = this.visibleStart; i <= this.visibleEnd; i++) {
            if (i >= this.data.length) break;
            
            const item = this.data[i];
            const itemElement = this.createItemElement(item, i);
            this.visibleContainer.appendChild(itemElement);
        }
    }
    
    createItemElement(item, index) {
        const div = document.createElement('div');
        div.className = 'sync-history-item virtual-item';
        div.style.height = `${this.itemHeight}px`;
        div.dataset.index = index;
        
        const statusClass = item.success ? 'success' : 'failed';
        const statusLabel = item.success ? '成功' : '失败';
        const time = this.formatTime(item.timestamp);
        const duration = item.duration_ms ? `${item.duration_ms}ms` : '--';
        const remote = `${item.remote_ip}::${item.remote_module}`;
        
        div.innerHTML = `
            <span class="sync-status ${statusClass}">${statusLabel}</span>
            <span class="event-type ${this.getEventTypeClass(item.event_type)}">${this.getEventTypeLabel(item.event_type)}</span>
            <span class="event-path">${this.escapeHtml(item.file_path)}</span>
            <span class="sync-remote">${this.escapeHtml(remote)}</span>
            <span class="sync-duration">${duration}</span>
            <span class="event-time">${time}</span>
        `;
        
        return div;
    }
    
    // 工具方法
    formatTime(timestamp) {
        if (!timestamp) return '--';
        const date = new Date(timestamp);
        const now = new Date();
        const diff = now - date;

        if (diff < 60000) {
            return '刚刚';
        } else if (diff < 3600000) {
            return Math.floor(diff / 60000) + ' 分钟前';
        } else {
            return date.toLocaleTimeString('zh-CN');
        }
    }
    
    getEventTypeClass(type) {
        const typeMap = {
            'CREATE_FILE': 'create',
            'CREATE_FOLDER': 'create',
            'MODIFY': 'modify',
            'CLOSE_WRITE': 'modify',
            'DELETE_FILE': 'delete',
            'DELETE_FOLDER': 'delete',
            'MOVE': 'move',
            'MOVED_FROM': 'move',
            'MOVED_TO': 'move'
        };
        return typeMap[type] || 'modify';
    }
    
    getEventTypeLabel(type) {
        const labelMap = {
            'CREATE_FILE': '创建',
            'CREATE_FOLDER': '创建',
            'MODIFY': '修改',
            'CLOSE_WRITE': '写入',
            'DELETE_FILE': '删除',
            'DELETE_FOLDER': '删除',
            'MOVE': '移动',
            'MOVED_FROM': '移出',
            'MOVED_TO': '移入'
        };
        return labelMap[type] || type;
    }
    
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
    
    // 滚动到指定位置
    scrollToIndex(index) {
        const scrollTop = index * this.itemHeight;
        this.scrollContainer.scrollTop = scrollTop;
    }
    
    // 获取当前可见范围
    getVisibleRange() {
        return {
            start: this.visibleStart,
            end: this.visibleEnd,
            total: this.data.length
        };
    }
}

// 导出到全局
window.VirtualScrollList = VirtualScrollList;