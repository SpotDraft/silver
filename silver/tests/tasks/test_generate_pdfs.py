import pytest
from mock import patch, call, MagicMock

from silver.tasks import generate_pdfs, generate_pdf
from silver.tests.factories import InvoiceFactory, ProformaFactory


@pytest.mark.django_db
def test_generate_pdfs_task(monkeypatch):
    issued_invoice = InvoiceFactory.create()
    issued_invoice.issue()

    paid_invoice = InvoiceFactory.create()
    paid_invoice.issue()
    paid_invoice.pay()

    canceled_invoice = InvoiceFactory.create()
    canceled_invoice.issue()
    canceled_invoice.cancel()

    issued_invoice_already_generated = InvoiceFactory.create()
    issued_invoice_already_generated.issue()
    issued_invoice_already_generated.pdf.dirty = False
    issued_invoice_already_generated.pdf.save()

    issued_proforma = ProformaFactory.create()
    issued_proforma.issue()

    issued_proforma_already_generated = ProformaFactory.create()
    issued_proforma_already_generated.issue()
    issued_proforma_already_generated.pdf.dirty = False
    issued_proforma_already_generated.pdf.save()

    documents_to_generate = [issued_invoice, canceled_invoice, paid_invoice,
                             issued_proforma]

    for document in documents_to_generate:
        assert document.pdf.dirty

    lock_manager_mock = MagicMock()
    monkeypatch.setattr('silver.tasks.lock_manager', lock_manager_mock)

    with patch('silver.tasks.generate_pdf') as generate_pdf_mock:
        generate_pdfs()

        generate_pdf_mock.assert_has_calls([call.delay(document.id, document.kind)
                                            for document in documents_to_generate],
                                           any_order=True)


@pytest.mark.django_db
def test_generate_pdfs_task_lock_not_owned(monkeypatch):
    issued_invoice = InvoiceFactory.create()
    issued_invoice.issue()

    issued_proforma = ProformaFactory.create()
    issued_proforma.issue()

    lock_manager_mock = MagicMock(return_value=None)
    monkeypatch.setattr('silver.tasks.lock_manager.lock', lock_manager_mock)

    with patch('silver.tasks.generate_pdf') as generate_pdf_mock:
        generate_pdfs()

        assert not generate_pdf_mock.called


@pytest.mark.django_db
def test_generate_pdf_task(settings, tmpdir, monkeypatch):
    settings.MEDIA_ROOT = tmpdir.strpath

    invoice = InvoiceFactory.create()
    invoice.issue()

    assert invoice.pdf.dirty

    generate_pdf_mock = MagicMock()

    monkeypatch.setattr('silver.models.documents.pdf.generate_pdf_template_object',
                        generate_pdf_mock)

    generate_pdf(invoice.id, invoice.kind)

    # pdf needs to be refreshed as the invoice reference in the test is not the same with the one
    # in the task
    invoice.pdf.refresh_from_db()

    assert not invoice.pdf.dirty

    assert invoice.pdf.url == settings.MEDIA_URL + invoice.get_pdf_upload_path()

    assert generate_pdf_mock.call_count == 1
