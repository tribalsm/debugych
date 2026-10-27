/** Only safe, user-facing messages cross the native/provider boundary. */
export class CompanionRequestError extends Error {
 constructor(readonly code:number|'offline'|'invalid',message?:string){super(message??String(code));this.name='CompanionRequestError';}
}
export function requestErrorMessage(error:unknown):string{
 if(error instanceof DOMException&&error.name==='AbortError')return 'Отправка отменена. Уже отправленный AI-вызов может расходовать резерв.';
 if(error instanceof CompanionRequestError){
  if(error.code===401||error.code===403)return 'Нет доступа к AI. Проверьте серверное подключение; ключи в питомце не вводятся.';
  if(error.code===429)return 'Достигнут лимит запросов или бюджета. Повторите вручную после его восстановления.';
  if(error.code===408||error.code===504)return 'Время ожидания истекло. Вопрос сохранён; автоматического повтора нет.';
  if(error.code===409)return 'Контекст или конфигурация изменились. Повторите вопрос с новым подтверждением.';
  if(error.code===428)return 'Для этого AI-вопроса нужно отдельное подтверждение отправки.';
  if(error.code==='invalid')return 'AI вернул ответ, который не удалось проверить. Он не показан как доказанный результат.';
  if(error.code==='offline')return 'Нет связи с сервером объяснений. Вопрос сохранён для ручного повтора.';
  return 'AI-провайдер сейчас недоступен. Вопрос сохранён; платных автоматических повторов нет.';
 }
 return 'Не удалось подготовить ответ. Вопрос сохранён для ручного повтора. Автоматических повторов нет.';
}
