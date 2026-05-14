import { AlertCircle, CheckCircle2, Info, X } from "lucide-react";
import styles from "./InfoCenter.module.css";

export interface AppMessage {
  id: string;
  title: string;
  body: string;
  createdAt: string;
  tone: "error" | "info";
  read: boolean;
}

function formatTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return new Intl.DateTimeFormat("zh-CN", {
    hour: "2-digit",
    minute: "2-digit"
  }).format(date);
}

export function InfoCenter({
  messages,
  unreadCount,
  isOpen,
  onOpen,
  onClose
}: {
  messages: AppMessage[];
  unreadCount: number;
  isOpen: boolean;
  onOpen: () => void;
  onClose: () => void;
}) {
  return (
    <div className={styles.infoCenter}>
      <button
        aria-label="信息中心"
        className={styles.iconButton}
        onClick={onOpen}
        type="button"
      >
        <Info aria-hidden="true" size={20} />
        {unreadCount > 0 && (
          <span className={styles.badge} aria-label={`${unreadCount} 条未读信息`}>
            {unreadCount > 99 ? "99+" : unreadCount}
          </span>
        )}
      </button>

      {isOpen && (
        <section aria-label="信息弹窗" className={styles.panel}>
          <div className={styles.panelHeader}>
            <div>
              <h2>信息</h2>
              <p>抓取异常和系统提示会显示在这里</p>
            </div>
            <button
              aria-label="关闭信息弹窗"
              className={styles.closeButton}
              onClick={onClose}
              type="button"
            >
              <X aria-hidden="true" size={18} />
            </button>
          </div>

          <div className={styles.messageList}>
            {messages.length ? (
              messages.map((message) => (
                <article
                  className={styles.message}
                  data-tone={message.tone}
                  key={message.id}
                >
                  <div className={styles.messageIcon}>
                    {message.tone === "error" ? (
                      <AlertCircle aria-hidden="true" size={18} />
                    ) : (
                      <CheckCircle2 aria-hidden="true" size={18} />
                    )}
                  </div>
                  <div>
                    <div className={styles.messageTitleRow}>
                      <h3>{message.title}</h3>
                      <time>{formatTime(message.createdAt)}</time>
                    </div>
                    <p>{message.body}</p>
                  </div>
                </article>
              ))
            ) : (
              <div className={styles.empty}>
                <CheckCircle2 aria-hidden="true" size={22} />
                <strong>暂无异常信息</strong>
                <span>抓取失败或后端不可用时，会在这里提醒。</span>
              </div>
            )}
          </div>
        </section>
      )}
    </div>
  );
}
