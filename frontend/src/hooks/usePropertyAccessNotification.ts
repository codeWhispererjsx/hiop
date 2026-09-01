import { useRequest } from "../hooks/useRequest";
import { endpoints } from "../lib/api";

export function usePropertyAccessNotification() {
  const { data, loading, error, reload } = useRequest(() => endpoints.propertyAccessNotifications(), []);
  return { notifications: data ?? [], loading, error, reload };
}
