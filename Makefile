default: help

help:
	@echo "Use setup.py to build"
	@echo "Extra make targets available:"
	@echo " install-autostart - install autostart files (xdg)"
	@echo " install-icons - install icons"
	@echo " install - calls all of the above (but calling setup.py is still necessary)"

install-icons:
	mkdir -p $(DESTDIR)/usr/share/icons/hicolor/scalable/apps
	cp icons/delete_icon.svg $(DESTDIR)/usr/share/icons/hicolor/scalable/apps/qubes-delete.svg
	cp icons/ok_icon.svg $(DESTDIR)/usr/share/icons/hicolor/scalable/apps/qubes-ok.svg
	cp icons/padlock_icon.svg $(DESTDIR)/usr/share/icons/hicolor/scalable/apps/qubes-padlock.svg
	cp icons/qubes-info.svg $(DESTDIR)/usr/share/icons/hicolor/scalable/apps/qubes-info.svg
	cp icons/qubes-key.svg $(DESTDIR)/usr/share/icons/hicolor/scalable/apps/qubes-key.svg
	cp icons/qubes_ask.svg $(DESTDIR)/usr/share/icons/hicolor/scalable/apps/qubes-ask.svg
	cp icons/qubes_customize.svg $(DESTDIR)/usr/share/icons/hicolor/scalable/apps/qubes-customize.svg
	cp icons/qubes_expander_hidden.svg $(DESTDIR)/usr/share/icons/hicolor/scalable/apps/qubes-expander-hidden.svg
	cp icons/qubes_expander_shown.svg $(DESTDIR)/usr/share/icons/hicolor/scalable/apps/qubes-expander-shown.svg
	cp icons/qubes_logo.svg $(DESTDIR)/usr/share/icons/hicolor/scalable/apps/qubes-logo.svg
	cp icons/question_icon.svg $(DESTDIR)/usr/share/icons/hicolor/scalable/apps/qubes-question.svg
	cp icons/question_icon_light.svg $(DESTDIR)/usr/share/icons/hicolor/scalable/apps/qubes-question-light.svg
	cp icons/this-device-icon.svg $(DESTDIR)/usr/share/icons/hicolor/scalable/apps/qubes-this-device.svg

install-autostart:
	mkdir -p $(DESTDIR)/etc/xdg/autostart
	mkdir -p $(DESTDIR)/usr/share/applications

install: install-autostart install-icons

.PHONY: clean
clean:
