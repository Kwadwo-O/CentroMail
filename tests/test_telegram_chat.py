"""Telegram history, topic routing, safe retries and account photos without live delivery."""
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace as Item
from unittest.mock import AsyncMock, patch

import app as a
from test_integrations import IntegrationFixture


@unittest.skipUnless(a.TELETHON_AVAILABLE, 'Telethon is not installed')
class TelegramChatTests(IntegrationFixture):
    def setUp(self):
        super().setUp()
        self.login()
        self.config={'stage':'connected','session':'private-session','api_id':123,'api_hash':'a'*32}
        with a.app.app_context():a.save_integration(self.user_id,'telegram',self.config)
        self.dialog=Item(id=-100123,name='Study group',entity=Item(forum=False),input_entity=a.telegram_types.InputPeerChannel(123,456),is_group=True,is_channel=True,unread_count=2,message=None)
        self.telegram=AsyncMock()
        self.telegram.is_user_authorized.return_value=True
        self.telegram.get_dialogs.return_value=[self.dialog]
        self.telegram.get_messages.return_value=[self.message(2,'Newest'),self.message(1,'Older')]
        self.client_patch=patch.object(a,'_telegram_client',return_value=self.telegram)
        self.client_patch.start();self.addCleanup(self.client_patch.stop)

    def message(self,identifier,text,*,root=None,out=False):
        return Item(id=identifier,message=text,out=out,date=datetime.now(timezone.utc),sender=Item(first_name='Friend',last_name='',username='friend'),reply_to=Item(reply_to_top_id=root,reply_to_msg_id=root,forum_topic=bool(root)))

    def topic(self,identifier,title,closed=False):
        return a.telegram_types.ForumTopic(id=identifier,date=datetime.now(timezone.utc),peer=a.telegram_types.PeerChannel(123),title=title,icon_color=0,top_message=identifier,read_inbox_max_id=0,read_outbox_max_id=0,unread_count=0,unread_mentions_count=0,unread_reactions_count=0,unread_poll_votes_count=0,from_id=a.telegram_types.PeerUser(1),notify_settings=a.telegram_types.PeerNotifySettings(),closed=closed,hidden=False)

    def forum(self):
        self.dialog.entity.forum=True
        self.telegram.return_value=Item(topics=[self.topic(1,'General'),self.topic(20,'Homework'),self.topic(30,'Closed',True)])

    def post_chat(self,**values):
        return self.client.post('/api/integrations/telegram/chats/-100123',data={'csrf_token':'test-token','text':'Hello <everyone>','request_id':'a'*32,**values})

    def test_regular_groups_receive_chronological_messages_and_have_no_topics(self):
        response=self.client.get('/api/integrations/telegram/chats/-100123')
        self.assertEqual(response.status_code,200)
        self.assertEqual([message['text'] for message in response.json['messages']],['Older','Newest'])
        self.assertTrue(response.json['can_send']);self.assertFalse(response.json['forum'])
        self.telegram.get_messages.assert_awaited_once_with(self.dialog.input_entity,limit=50,offset_id=0)
        self.telegram.disconnect.assert_awaited_once()

    def test_regular_group_send_is_plain_text_and_retry_id_is_stable(self):
        for _ in range(2):self.assertEqual(self.post_chat().json,{'sent':True})
        requests=[call.args[0] for call in self.telegram.call_args_list]
        self.assertTrue(all(isinstance(request,a.telegram_functions.messages.SendMessageRequest) for request in requests))
        self.assertEqual(requests[0].random_id,requests[1].random_id)
        self.assertEqual(requests[0].message,'Hello <everyone>');self.assertIsNone(requests[0].reply_to)
        self.assertEqual(requests[0].peer,self.dialog.input_entity)
        self.assertTrue(requests[0].no_webpage)

    def test_forum_requires_a_topic_before_send_and_reads_only_selected_thread(self):
        self.forum()
        response=self.client.get('/api/integrations/telegram/chats/-100123')
        self.assertTrue(response.json['forum']);self.assertFalse(response.json['can_send'])
        self.telegram.get_messages.assert_not_awaited()
        self.assertEqual(self.post_chat().status_code,400)
        response=self.client.get('/api/integrations/telegram/chats/-100123?topic=20&before=100')
        self.assertEqual(response.status_code,200)
        self.telegram.get_messages.assert_awaited_once_with(self.dialog.input_entity,limit=50,offset_id=100,reply_to=20)
        response=self.post_chat(topic='20')
        self.assertEqual(response.json,{'sent':True})
        sent=self.telegram.call_args.args[0]
        self.assertEqual(sent.reply_to.reply_to_msg_id,20);self.assertIsNone(sent.reply_to.top_msg_id)

    def test_general_topic_excludes_other_topics_and_sends_to_general(self):
        self.forum()
        self.telegram.get_messages.return_value=[self.message(4,'Homework',root=20),self.message(3,'General reply',root=1),self.message(2,'General message')]
        created=self.message(20,'Topic creation')
        created.action=a.telegram_types.MessageActionTopicCreate(title='Homework',icon_color=0)
        self.telegram.get_messages.return_value.insert(0,created)
        response=self.client.get('/api/integrations/telegram/chats/-100123?topic=1')
        self.assertEqual([message['text'] for message in response.json['messages']],['General message','General reply'])
        self.assertEqual(self.post_chat(topic='1').status_code,200)
        self.assertIsNone(self.telegram.call_args.args[0].reply_to)

    def test_topic_search_reaches_the_provider_without_loading_unrelated_history(self):
        self.forum()
        response=self.client.get('/api/integrations/telegram/chats/-100123?topic_search=Homework')
        self.assertEqual(response.status_code,200)
        request=self.telegram.call_args.args[0]
        self.assertIsInstance(request,a.telegram_functions.messages.GetForumTopicsRequest)
        self.assertEqual(request.q,'Homework');self.assertEqual(request.limit,100)
        self.telegram.get_messages.assert_not_awaited()

    def test_incoming_messages_are_paged_without_skipping_a_busy_chat(self):
        self.telegram.get_messages.return_value=[self.message(identifier,str(identifier)) for identifier in range(51,101)]
        response=self.client.get('/api/integrations/telegram/chats/-100123?after=50')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json['messages'][0]['id'],'51')
        self.assertEqual(response.json['latest_seen'],'100')
        self.assertTrue(response.json['has_more_new'])
        self.telegram.get_messages.assert_awaited_once_with(self.dialog.input_entity,limit=50,offset_id=0,min_id=50,reverse=True)

    def test_selected_topic_remains_available_outside_the_recent_topic_list(self):
        self.forum()
        self.telegram.side_effect=[Item(topics=[self.topic(1,'General')]),Item(topics=[self.topic(20,'Homework')])]
        response=self.client.get('/api/integrations/telegram/chats/-100123?topic=20')
        self.assertEqual(response.status_code,200)
        self.assertTrue(response.json['can_send'])
        self.assertIsInstance(self.telegram.call_args.args[0],a.telegram_functions.messages.GetForumTopicsByIDRequest)

    def test_closed_unknown_and_topics_disabled_destinations_do_not_send(self):
        self.forum()
        for topic in ('30','999'):
            self.assertEqual(self.post_chat(topic=topic).status_code,400)
        self.assertFalse(any(isinstance(call.args[0],a.telegram_functions.messages.SendMessageRequest) for call in self.telegram.call_args_list))
        self.dialog.entity.forum=False
        self.assertEqual(self.post_chat(topic='20').status_code,400)

    def test_read_only_groups_and_channels_cannot_send(self):
        for rights in (Item(broadcast=True),Item(default_banned_rights=Item(send_plain=True)),Item(banned_rights=Item(send_messages=True))):
            self.dialog.entity=rights
            self.assertFalse(self.client.get('/api/integrations/telegram/chats/-100123').json['can_send'])
            self.assertEqual(self.post_chat().status_code,400)
        self.telegram.assert_not_awaited()

    def test_other_users_and_unknown_chats_cannot_access_messages_or_photos(self):
        anonymous=a.app.test_client()
        self.assertEqual(anonymous.get('/api/integrations/telegram/chats/-100123').status_code,302)
        self.assertEqual(anonymous.get('/api/integrations/telegram/chats/-100123/photo').status_code,302)
        with a.app.app_context():a.delete_integration(self.user_id,'telegram')
        self.assertEqual(self.client.get('/api/integrations/telegram/chats/-100123').status_code,409)
        self.telegram.get_messages.assert_not_awaited()
        with a.app.app_context():a.save_integration(self.user_id,'telegram',self.config)
        self.assertEqual(self.client.get('/api/integrations/telegram/chats/-999').status_code,400)
        self.assertEqual(self.client.get('/api/integrations/telegram/chats/-999/photo').status_code,404)
        self.telegram.download_profile_photo.assert_not_awaited()

    def test_invalid_input_and_missing_csrf_never_reach_telegram(self):
        for values in ({'text':''},{'text':'😀'*2049},{'request_id':'invalid'},{'topic':'bad'}):
            self.assertEqual(self.post_chat(**values).status_code,400)
        self.assertEqual(self.client.post('/api/integrations/telegram/chats/-100123',data={'text':'Hello'}).status_code,400)
        self.telegram.connect.assert_not_awaited()

    def test_failed_send_disconnects_and_keeps_an_honest_error(self):
        self.telegram.side_effect=TimeoutError()
        response=self.post_chat()
        self.assertEqual(response.status_code,502)
        self.assertIn('draft is kept',response.json['error'])
        self.telegram.disconnect.assert_awaited_once()

    def test_profile_photos_are_private_jpegs_and_missing_photos_fall_back(self):
        self.telegram.download_profile_photo.return_value=b'\xff\xd8\xffphoto'
        response=self.client.get('/api/integrations/telegram/chats/-100123/photo')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.mimetype,'image/jpeg');self.assertEqual(response.headers['Cache-Control'],'no-store')
        self.telegram.download_profile_photo.assert_awaited_once_with(self.dialog.entity,file=bytes,download_big=False)
        self.telegram.download_profile_photo.return_value=None
        self.assertEqual(self.client.get('/api/integrations/telegram/chats/me/photo').status_code,404)
        self.telegram.download_profile_photo.assert_awaited_with('me',file=bytes,download_big=False)

    def test_conversation_snapshot_includes_groups_topics_and_unread_counts(self):
        self.telegram.get_me.return_value=Item(first_name='Tester')
        response=self.client.get('/api/integrations/telegram/messages')
        self.assertEqual(response.json['messages'][0]['chat_id'],'-100123')
        self.assertEqual(response.json['messages'][0]['kind'],'group')
        self.assertEqual(response.json['messages'][0]['unread'],2)
        self.assertNotIn('private-session',response.text)
        self.telegram.get_dialogs.assert_awaited_once_with(limit=50)
