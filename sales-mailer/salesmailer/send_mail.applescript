-- Mac の「メール」アプリで1通送信する
-- 引数: 宛先 件名 本文 差出人（空なら既定のアカウント）
on run argv
	set theTo to item 1 of argv
	set theSubject to item 2 of argv
	set theBody to item 3 of argv
	set theSender to item 4 of argv
	tell application "Mail"
		set msg to make new outgoing message with properties {subject:theSubject, content:theBody, visible:false}
		if theSender is not "" then set sender of msg to theSender
		tell msg to make new to recipient at end of to recipients with properties {address:theTo}
		send msg
	end tell
end run
