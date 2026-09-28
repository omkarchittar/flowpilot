"use client";
import Link from "next/link";
import { useState } from "react";
import { ArrowUpRight, Bell, Check } from "lucide-react";
import { useAuth } from "@/components/auth";
import { api, errorMessage } from "@/lib/api";
import { dateTime } from "@/lib/format";
import { useResource } from "@/lib/use-resource";
import type { Notification } from "@/lib/types";
import {
  Empty,
  ErrorNotice,
  Loading,
  PageHeading,
  Panel,
} from "@/components/ui";
export default function Notifications() {
  const resource = useResource<Notification[]>("/notifications", 10000);
  const { session } = useAuth();
  const [busy, setBusy] = useState<string>();
  const [error, setError] = useState<string>();
  return (
    <>
      <PageHeading
        eyebrow="Your updates"
        title="Inbox"
        description="Completion notifications for your vendor requests. Delivered here, in your workspace."
      />
      <ErrorNotice message={resource.error ?? error} retry={resource.refresh} />
      <Panel
        title="Recent notifications"
        subtitle="Your latest 100 notifications"
      >
        {resource.data ? (
          resource.data.length ? (
            <ul className="notification-list">
              {resource.data.map((notification) => (
                <li
                  key={notification.id}
                  className={!notification.read_at ? "unread" : ""}
                >
                  <span className="notification-icon">
                    <Bell size={19} />
                  </span>
                  <div>
                    <div className="notification-heading">
                      <strong>{notification.subject}</strong>
                      {!notification.read_at && (
                        <span className="unread-dot" aria-label="Unread" />
                      )}
                    </div>
                    <p>{notification.message}</p>
                    <time dateTime={notification.created_at}>
                      {dateTime(notification.created_at)}
                    </time>
                    <div className="notification-actions">
                      <Link
                        className="text-link"
                        href={`/workflows/${notification.workflow_id}`}
                      >
                        View request
                        <ArrowUpRight size={14} />
                      </Link>
                      {!notification.read_at && (
                        <button
                          className="text-button"
                          disabled={busy === notification.id}
                          onClick={async () => {
                            setBusy(notification.id);
                            setError(undefined);
                            try {
                              await api(
                                `/notifications/${notification.id}/read`,
                                { method: "POST" },
                                session!.csrf_token,
                              );
                              resource.refresh();
                            } catch (cause) {
                              setError(errorMessage(cause));
                            } finally {
                              setBusy(undefined);
                            }
                          }}
                        >
                          <Check size={14} />
                          Mark as read
                        </button>
                      )}
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <Empty
              title="You’re all caught up"
              text="When one of your approved requests completes, its notification will appear here."
            />
          )
        ) : !resource.error ? (
          <Loading />
        ) : null}
      </Panel>
    </>
  );
}
